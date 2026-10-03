# SPDX-License-Identifier: MIT
"""Loopback ASGI consumer for a verified, immutable ellmos-system-gui kit."""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote
import zipfile
from datetime import datetime, timezone

from tools.gui_consumer import DEFAULT_PIN, InspectionError, _read_pin, _safe_name, inspect_archive, inspect_installation

CAP_SCHEMA = "ellmos-system-gui.capabilities.v1"
BRAND_SCHEMA = "ellmos-system-gui.brand.v1"
ORIGIN_SCHEMA = "ellmos-system-gui.backend-origin.v1"
DEFAULT_BRAND = {
    "schema": BRAND_SCHEMA, "label": "Ocean", "product": "Open Ocean",
    "logo_text": "OCEAN", "logo_path": None, "theme": "ocean",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brand_from_file(path: Path | None) -> dict:
    if path is None:
        return dict(DEFAULT_BRAND)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InspectionError("brand_config_invalid")
    brand = {"schema": BRAND_SCHEMA}
    for key in ("label", "product", "logo_text"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 80 or any(ord(c) < 32 for c in value):
            raise InspectionError("brand_config_invalid")
        brand[key] = value.strip()
    theme = data.get("theme")
    if theme not in ("dark", "light", "ocean", "warm"):
        raise InspectionError("brand_config_invalid")
    brand["theme"] = theme
    logo = data.get("logo_path")
    if logo is not None and (
        not isinstance(logo, str) or not logo.startswith("/static/branding/")
        or not logo.endswith((".png", ".webp")) or not _safe_name(logo.lstrip("/"))
    ):
        raise InspectionError("brand_config_invalid")
    # No consumer branding asset is bundled in this adapter.
    if logo is not None:
        raise InspectionError("brand_asset_unavailable")
    brand["logo_path"] = None
    return brand


def _safe_url_path(raw: str) -> str | None:
    if not raw.startswith("/") or "%" in raw and ("%2f" in raw.lower() or "%5c" in raw.lower()):
        return None
    try:
        path = unquote(raw, encoding="utf-8", errors="strict")
    except UnicodeError:
        return None
    if "\\" in path or any(ord(c) < 32 for c in path) or "//" in path:
        return None
    if path == "/":
        return "index.html"
    candidate = path.lstrip("/")
    return candidate if _safe_name(candidate) else None


def _asset_candidates(path: str) -> tuple[str, ...]:
    if path == "index.html":
        return (path,)
    if path.endswith("/"):
        return (path + "index.html",)
    if "." not in Path(path).name:
        return (path + "/index.html", path + ".html")
    return (path,)


def _type(name: str) -> str:
    if name.endswith(".html"):
        return "text/html; charset=utf-8"
    if name.endswith(".js"):
        return "text/javascript; charset=utf-8"
    if name.endswith(".css"):
        return "text/css; charset=utf-8"
    guess = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return guess + ("; charset=utf-8" if guess.startswith("text/") else "")


async def _reply(send, status: int, body: bytes, content_type: str, method: str, *, no_store: bool = True) -> None:
    headers = [
        (b"content-type", content_type.encode("ascii")),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"x-content-type-options", b"nosniff"),
        (b"cache-control", b"no-store" if no_store else b"public, max-age=31536000, immutable"),
        (b"content-security-policy", b"default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": b"" if method == "HEAD" else body})


class OceanGuiApp:
    """Serve only dist-manifest-listed files from one verified archive."""

    def __init__(self, archive_path: Path, *, pin_path: Path = DEFAULT_PIN, brand_path: Path | None = None,
                 dist_root: Path | None = None, receipt_path: Path | None = None) -> None:
        self.archive_path = Path(archive_path)
        self.pin = _read_pin(pin_path)
        report = inspect_archive(self.archive_path, pin_path)
        if not report["dist_verified"]:
            raise InspectionError(str(report["reason_code"]), int(report.get("exit_code", 2)))
        self.archive_sha256 = self.pin["source"]["archive_sha256"]
        self.brand = _brand_from_file(brand_path)
        self.installation = inspect_installation(dist_root, receipt_path, self.archive_path, pin_path)
        with zipfile.ZipFile(self.archive_path) as archive:
            manifest = json.loads(archive.read("dist/dist-manifest.json").decode("utf-8"))
        self.files = frozenset(manifest["files"])
        self.file_hashes = dict(manifest["files"])
        self.observed_at = _utc_now()

    def _capabilities(self, *, served: bool = False) -> dict:
        return {
            "schema": CAP_SCHEMA, "schema_version": 1,
            "kit": {
                "revision": self.pin["source"]["commit"],
                "version": self.pin["version"],
                "archive_sha256": self.archive_sha256,
                "verified": True,
                "installed": self.installation["installed"],
                "installed_files_verified": self.installation["files_verified"],
                "served": served,
                "reason_code": self.installation["reason_code"],
            },
            "brand": self.brand,
            "modules": {
                "ellmos-system-gui": {
                    "adapter_registered": True, "runtime_verified": True if served else None,
                    "available": True if served else None,
                    "reason_code": "verified_static_shell" if served else "archive_verified_not_served",
                    "observed_at": self.observed_at if served else None,
                },
            },
            "missing_adapters": ["Ocean API route mapping", "device authorization", "module capability probes"],
            "observed_at": self.observed_at,
        }

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope.get("type") != "http":
            return
        method = str(scope.get("method") or "").upper()
        path = str(scope.get("path") or "")
        if method not in {"GET", "HEAD"}:
            await _reply(send, 405, b'{"reason_code":"method_unavailable"}', "application/json; charset=utf-8", method)
            return
        if path == "/api/gui/brand":
            payload = self.brand
        elif path == "/api/gui/backend-origin":
            payload = {
                "schema": ORIGIN_SCHEMA, "mode": "unknown", "declared_mode": None,
                "reason_code": "ocean_backend_adapter_unbound",
                "observed_at": None,
            }
        elif path == "/api/gui/capabilities":
            payload = self._capabilities(served=True)
        elif path.startswith("/api/"):
            await _reply(send, 503, b'{"reason_code":"ocean_api_adapter_unbound","status":"unavailable"}', "application/json; charset=utf-8", method)
            return
        else:
            payload = None
        if payload is not None:
            body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            await _reply(send, 200, body, "application/json; charset=utf-8", method)
            return
        safe = _safe_url_path(path)
        if safe is None:
            await _reply(send, 404, b"", "text/plain; charset=utf-8", method)
            return
        name = next((item for item in _asset_candidates(safe) if item in self.files), None)
        if name is None:
            await _reply(send, 404, b"", "text/plain; charset=utf-8", method)
            return
        try:
            with zipfile.ZipFile(self.archive_path) as archive:
                data = archive.read("dist/" + name)
        except (OSError, KeyError, zipfile.BadZipFile):
            await _reply(send, 503, b"", "text/plain; charset=utf-8", method)
            return
        from hashlib import sha256
        if sha256(data).hexdigest() != self.file_hashes[name]:
            await _reply(send, 503, b"", "text/plain; charset=utf-8", method)
            return
        await _reply(send, 200, data, _type(name), method, no_store=name.endswith(".html"))
