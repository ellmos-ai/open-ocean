"""ASGI boundary that makes the dedicated OCEAN origin product-owned.

The selected runtime provider may expose its own domain UI, PWA manifest and
root-scoped service worker.  Those surfaces are valid for the provider when it
runs standalone, but they must not claim OCEAN's dedicated browser origin.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any


AsgiApp = Callable[[dict[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]], Awaitable[None]]


_CLEANUP_SCRIPT = """<script data-ocean-origin-cleanup>
(async () => {
  let changed = false;
  const legacyCachePrefixes = ["ellmos-core-pwa"];
  if ("serviceWorker" in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const rootScope = `${window.location.origin}/`;
    const rootRegistrations = registrations.filter((item) => item.scope === rootScope);
    const results = await Promise.all(rootRegistrations.map((item) => item.unregister()));
    changed = results.some(Boolean) || changed;
  }
  if ("caches" in window) {
    const names = await caches.keys();
    const legacyNames = names.filter((name) =>
      legacyCachePrefixes.some((prefix) => name.startsWith(prefix))
    );
    const results = await Promise.all(legacyNames.map((name) => caches.delete(name)));
    changed = results.some(Boolean) || changed;
  }
  if (changed && !sessionStorage.getItem("ocean-origin-cleaned-v1")) {
    sessionStorage.setItem("ocean-origin-cleaned-v1", "1");
    window.location.reload();
  }
})().catch(() => {});
</script>"""


_CLEANUP_WORKER = """self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => names.filter((name) => name.startsWith("ellmos-core-pwa")))
      .then((names) => Promise.all(names.map((name) => caches.delete(name))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll({type: "window"}))
      .then((clients) => Promise.all(clients.map((client) => client.navigate(client.url))))
  );
});
"""


def _headers(*items: tuple[str, str]) -> list[tuple[bytes, bytes]]:
    return [(key.encode("latin-1"), value.encode("latin-1")) for key, value in items]


async def _respond(
    send: Callable[..., Awaitable[None]],
    *,
    status: int,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
    head_only: bool,
) -> None:
    complete_headers = [
        *headers,
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    await send({"type": "http.response.start", "status": status, "headers": complete_headers})
    await send({"type": "http.response.body", "body": b"" if head_only else body, "more_body": False})


class OceanOriginApp:
    """Own root/PWA identity and delegate the remaining provider API."""

    def __init__(self, provider: AsgiApp, *, prefix: str = "/control", title: str = "OCEAN Full Dev") -> None:
        normalized = "/" + prefix.strip("/")
        if normalized == "/":
            raise ValueError("OCEAN operator prefix must not be the origin root")
        self.provider = provider
        self.prefix = normalized
        self.title = title

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.provider(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "GET").upper()
        if method in {"GET", "HEAD"}:
            handled = await self._product_surface(path, method == "HEAD", send)
            if handled:
                return
        if method == "GET" and (path == self.prefix or path.startswith(self.prefix + "/")):
            await self._delegate_ocean_html(scope, receive, send)
            return
        await self.provider(scope, receive, send)

    async def _product_surface(self, path: str, head_only: bool, send) -> bool:
        no_store = ("cache-control", "no-store")
        if path == "/":
            await _respond(
                send,
                status=307,
                body=b"",
                headers=_headers(("location", self.prefix + "/"), no_store),
                head_only=head_only,
            )
            return True
        if path == "/manifest.webmanifest":
            manifest = {
                "name": self.title,
                "short_name": "OCEAN",
                "description": "Lokale OCEAN-Operatoroberfläche.",
                "start_url": self.prefix + "/",
                "scope": self.prefix + "/",
                "display": "standalone",
                "background_color": "#071a2d",
                "theme_color": "#0b4f6c",
                "lang": "de",
            }
            body = (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            await _respond(
                send,
                status=200,
                body=body,
                headers=_headers(("content-type", "application/manifest+json; charset=utf-8"), no_store),
                head_only=head_only,
            )
            return True
        if path == "/sw.js":
            await _respond(
                send,
                status=200,
                body=_CLEANUP_WORKER.encode("utf-8"),
                headers=_headers(
                    ("content-type", "application/javascript; charset=utf-8"),
                    ("service-worker-allowed", "/"),
                    no_store,
                ),
                head_only=head_only,
            )
            return True
        if path == "/offline":
            body = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self.title} offline</title></head><body><main><h1>{self.title} ist gerade offline.</h1>
<p>Bitte stelle die lokale Verbindung wieder her und öffne OCEAN danach erneut.</p></main></body></html>
""".encode("utf-8")
            await _respond(
                send,
                status=200,
                body=body,
                headers=_headers(("content-type", "text/html; charset=utf-8"), no_store),
                head_only=head_only,
            )
            return True
        return False

    async def _delegate_ocean_html(self, scope, receive, send) -> None:
        start: dict[str, Any] | None = None
        bodies: list[bytes] = []

        async def capture(message: dict[str, Any]) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] == "http.response.body":
                bodies.append(bytes(message.get("body", b"")))
                if message.get("more_body", False):
                    return
                await flush()
                return
            await send(message)

        async def flush() -> None:
            if start is None:
                raise RuntimeError("provider emitted a response body before response start")
            headers = list(start.get("headers", []))
            content_type = next(
                (value.decode("latin-1").lower() for key, value in headers if key.lower() == b"content-type"),
                "",
            )
            content_encoding = next(
                (value for key, value in headers if key.lower() == b"content-encoding"),
                b"",
            )
            body = b"".join(bodies)
            if content_type.startswith("text/html") and not content_encoding and b"data-ocean-origin-cleanup" not in body:
                marker = body.lower().rfind(b"</body>")
                script = _CLEANUP_SCRIPT.encode("utf-8")
                body = body[:marker] + script + body[marker:] if marker >= 0 else body + script
                headers = [
                    (key, value)
                    for key, value in headers
                    if key.lower() not in {b"content-length", b"cache-control"}
                ]
                headers.extend([
                    (b"cache-control", b"no-store"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ])
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.provider(scope, receive, capture)
