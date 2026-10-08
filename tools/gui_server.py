# SPDX-License-Identifier: MIT
"""Loopback ASGI consumer for a verified, immutable ellmos-system-gui kit."""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime, timezone

from tools.gui_consumer import (
    DEFAULT_PIN, MANIFEST, InspectionError, VerifiedGuiRelease, _read_pin, _safe_name,
    inspect_installation, verify_gui_archive,
)

CAP_SCHEMA = "ellmos.gui.capabilities.v1"
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
    return candidate if _safe_name(candidate.rstrip("/")) else None


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
        self.release = verify_gui_archive(self.archive_path, self.pin["source"]["commit"], self.pin["source"]["archive_sha256"])
        self.archive_sha256 = self.release.archive_sha256
        self.brand = _brand_from_file(brand_path)
        self.installation = inspect_installation(dist_root, receipt_path, self.archive_path, pin_path)
        self._configure_static()

    def _configure_static(self) -> None:
        manifest = json.loads(self.release.payload[MANIFEST])
        self.files = frozenset(manifest["files"])
        self.file_hashes = dict(manifest["files"])
        self.observed_at = _utc_now()

    @classmethod
    def from_verified_release(cls, release: VerifiedGuiRelease) -> "OceanGuiApp":
        """Reuse the native static consumer inside a provider-authorized origin."""
        instance = cls.__new__(cls)
        instance.release = release
        instance.archive_sha256 = release.archive_sha256
        instance.brand = dict(DEFAULT_BRAND)
        instance.pin = {"source": {"commit": release.source_commit}, "version": None}
        instance.installation = {"installed": False, "files_verified": 0, "reason_code": "install_receipt_unavailable"}
        instance._configure_static()
        return instance

    def _capabilities(self, *, served: bool = False) -> dict:
        from tools.gui_bridge import GuiBridge
        # Standalone shell metadata is public. Provider session/auth and native
        # adapters are not mounted by this command; no route is inferred live.
        report = GuiBridge().capabilities()
        for endpoint in report["endpoints"]:
            endpoint.update(available=False, provider=None, auth="none",
                            reason="ocean_api_adapter_unbound")
        for path in ("/api/gui/brand", "/api/gui/backend-origin", "/api/gui/capabilities"):
            report["endpoints"] = [item for item in report["endpoints"] if item["path"] != path]
            report["endpoints"].append({"method": "GET", "path": path, "kind": "read",
                "available": True, "provider": {"id": "open-ocean", "adapter_version": "1"},
                "auth": "none", "public_metadata": True, "runtime_verified": False,
                "verification_scope": "adapter", "reason": None})
        for item in report["modules"].values():
            item.update(adapter_registered=False, available=False, runtime_verified=None,
                        reason_code="ocean_api_adapter_unbound")
        report["modules"]["ellmos-system-gui"] = {
            "adapter_registered": True, "runtime_verified": None, "available": True,
            "verification_scope": "adapter", "reason_code": "verified_static_shell",
        }
        report.update(schema=CAP_SCHEMA, schema_version=1, brand=self.brand,
            kit={"revision": self.release.source_commit, "version": self.pin["version"],
                "archive_sha256": self.archive_sha256, "verified": True,
                "installed": self.installation["installed"],
                "installed_files_verified": self.installation["files_verified"],
                "served": served, "reason_code": self.installation["reason_code"]},
            gui={"status": "installed" if self.installation["installed"] else "unavailable",
                "reason_code": self.installation["reason_code"],
                "source_commit": self.release.source_commit, "archive_sha256": self.archive_sha256},
            missing_adapters=["Ocean API route mapping", "device authorization", "module capability probes"],
            observed_at=self.observed_at)
        for page in report["pages"]:
            safe = _safe_url_path(page["path"])
            declared = safe is not None and any(name in self.files for name in _asset_candidates(safe))
            page["missing"] = [item for item in page["missing"] if item != "verified-gui-release"]
            if not declared:
                page["missing"].append("declared-static-page")
            page["status"] = "configured" if not page["missing"] else "unavailable"
        return report

    async def serve_static(self, scope, send, *, html_transform=None) -> bool:
        """The single static-serving engine; false leaves provider routes alone."""
        method = str(scope.get("method") or "").upper()
        path = str(scope.get("path") or "")
        if method not in {"GET", "HEAD"} or path.startswith(("/api/", "/login", "/logout", "/register")):
            return False
        safe = _safe_url_path(path)
        name = next((item for item in _asset_candidates(safe) if item in self.files), None) if safe else None
        if name is None:
            return False
        data = self.release.payload["dist/" + name]
        if html_transform is not None and name.endswith(".html"):
            data = html_transform(data)
        await _reply(send, 200, data, _type(name), method, no_store=name.endswith(".html"))
        return True

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
        if not await self.serve_static(scope, send):
            await _reply(send, 404, b"", "text/plain; charset=utf-8", method)
