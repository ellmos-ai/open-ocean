"""Synthetic, offline contract tests for the pinned Ocean GUI consumer."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.gui_consumer import inspect_archive, inspect_installation
from tools.gui_server import OceanGuiApp

COMMIT = "a" * 40


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(root: Path, *, malicious_name: str | None = None):
    files = {
        "index.html": b"<!doctype html><html lang='de'><title>Ocean</title></html>",
        "assets/app.js": b"document.body.dataset.ready='1';",
    }
    manifest = {
        "schema": "ellmos-system-gui.dist.v1", "source_commit": COMMIT,
        "files": {name: digest(blob) for name, blob in files.items()},
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    archive = root / "kit.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as handle:
        for name, blob in files.items():
            handle.writestr("dist/" + name, blob)
        handle.writestr("dist/dist-manifest.json", manifest_bytes)
        handle.writestr("LICENSE", b"MIT License\n")
        if malicious_name:
            handle.writestr(malicious_name, b"unsafe")
    pin = {
        "schema": "ellmos.open-ocean.gui-consumer.v1", "id": "ellmos-system-gui",
        "version": "0.1.2", "status": "pinned_artifact_only", "activation_ready": False,
        "source": {"repository": "ellmos-ai/ellmos-system-gui", "commit": COMMIT,
                   "archive_sha256": digest(archive.read_bytes()),
                   "dist_manifest_schema": "ellmos-system-gui.dist.v1"},
        "required_backend_routes": [
            "/api/gui/brand", "/api/gui/backend-origin", "/api/gui/capabilities"],
    }
    pin_path = root / "pin.json"
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    return archive, pin_path, files, manifest_bytes


async def request(app, path: str, method: str = "GET"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "path": path, "method": method}, receive, send)
    status = messages[0]["status"]
    body = b"".join(m.get("body", b"") for m in messages[1:])
    return status, body


class GuiConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive, self.pin, self.files, self.manifest = fixture(self.root)

    def test_verified_archive_is_not_an_installation(self):
        report = inspect_archive(self.archive, self.pin)
        self.assertTrue(report["dist_verified"])
        self.assertEqual(report["dist_files_verified"], 2)
        self.assertFalse(inspect_installation(None, None, self.archive, self.pin)["installed"])

    def test_hash_mismatch_and_traversal_fail_closed(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"x")
        self.assertEqual(inspect_archive(self.archive, self.pin)["reason_code"], "archive_hash_mismatch")
        evil, evil_pin, _, _ = fixture(self.root, malicious_name="../escape.txt")
        self.assertEqual(inspect_archive(evil, evil_pin)["reason_code"], "archive_member_path_invalid")

    def test_zip_symlink_member_rejected(self):
        import stat
        with zipfile.ZipFile(self.archive, "a") as handle:
            info = zipfile.ZipInfo("dist/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            handle.writestr(info, "index.html")
        pin = json.loads(self.pin.read_text(encoding="utf-8"))
        pin["source"]["archive_sha256"] = digest(self.archive.read_bytes())
        self.pin.write_text(json.dumps(pin), encoding="utf-8")
        self.assertEqual(inspect_archive(self.archive, self.pin)["reason_code"], "archive_member_path_invalid")

    def test_install_receipt_and_all_local_hashes(self):
        dist = self.root / "dist"
        dist.mkdir()
        for name, blob in self.files.items():
            path = dist / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        (dist / "dist-manifest.json").write_bytes(self.manifest)
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps({
            "schema": "ellmos.open-ocean.gui-install-receipt.v1",
            "kit_id": "ellmos-system-gui", "version": "0.1.2",
            "source_commit": COMMIT, "archive_sha256": digest(self.archive.read_bytes()),
            "manifest_sha256": digest(self.manifest), "file_count": len(self.files),
        }), encoding="utf-8")
        result = inspect_installation(dist, receipt, self.archive, self.pin)
        self.assertTrue(result["installed"])
        self.assertEqual(result["files_verified"], 2)
        (dist / "assets/app.js").write_bytes(b"tampered")
        self.assertEqual(inspect_installation(dist, receipt, self.archive, self.pin)["reason_code"],
                         "install_file_hash_mismatch")

    def test_ocean_cli_check_does_not_start_server(self):
        import contextlib
        import ocean
        from unittest.mock import patch
        output = io.StringIO()
        with patch("tools.gui_consumer.DEFAULT_PIN", self.pin), contextlib.redirect_stdout(output):
            code = ocean.main(["gui", "--archive", str(self.archive), "--json"])
        self.assertEqual(code, 0)
        cli_report = json.loads(output.getvalue())
        self.assertFalse(cli_report["kit"]["installed"])
        self.assertFalse(cli_report["kit"]["served"])
        self.assertIsNone(cli_report["modules"]["ellmos-system-gui"]["runtime_verified"])
        self.assertIn("gui", ocean.build_parser().format_help())

    def test_gui_serve_requires_explicit_flag_and_loopback(self):
        import contextlib
        import ocean
        import types
        from unittest.mock import Mock, patch
        stub = types.SimpleNamespace(run=Mock())
        with patch("tools.gui_consumer.DEFAULT_PIN", self.pin), patch.dict(
            "sys.modules", {"uvicorn": stub}
        ), contextlib.redirect_stdout(io.StringIO()):
            code = ocean.main(["gui", "--archive", str(self.archive), "--serve"])
        self.assertEqual(code, 0)
        self.assertEqual(stub.run.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(stub.run.call_args.kwargs["lifespan"], "off")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                ocean.main(["gui", "--archive", str(self.archive), "--host", "0.0.0.0", "--serve"])

    def test_api_brand_origin_capabilities_and_static_routes(self):
        app = OceanGuiApp(self.archive, pin_path=self.pin)
        status, body = asyncio.run(request(app, "/api/gui/brand"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["label"], "Ocean")
        status, body = asyncio.run(request(app, "/api/gui/backend-origin"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["mode"], "unknown")
        status, body = asyncio.run(request(app, "/api/gui/capabilities"))
        cap = json.loads(body)
        self.assertEqual(cap["schema_version"], 1)
        self.assertFalse(cap["kit"]["installed"])
        self.assertTrue(cap["kit"]["verified"])
        self.assertEqual(cap["modules"]["ellmos-system-gui"]["available"], True)
        status, body = asyncio.run(request(app, "/"))
        self.assertEqual((status, body), (200, self.files["index.html"]))
        status, body = asyncio.run(request(app, "/assets/app.js"))
        self.assertEqual((status, body), (200, self.files["assets/app.js"]))
        status, body = asyncio.run(request(app, "/api/tasks"))
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["reason_code"], "ocean_api_adapter_unbound")
        for path in ("/../LICENSE", "/%2e%2e/LICENSE", "/x\\y", "/private.txt"):
            status, _ = asyncio.run(request(app, path))
            self.assertEqual(status, 404, path)
        status, _ = asyncio.run(request(app, "/api/gui/brand", "POST"))
        self.assertEqual(status, 405)


if __name__ == "__main__":
    unittest.main()
