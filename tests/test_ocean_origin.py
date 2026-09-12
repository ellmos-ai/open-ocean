"""Regression tests for the OCEAN-owned browser origin."""

from __future__ import annotations

import asyncio
import json

from tools.ocean_origin import OceanOriginApp


class _ProviderApp:
    async def __call__(self, scope, receive, send):
        body = b"<html><head><title>provider</title></head><body>provider</body></html>"
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body, "more_body": False})


def _request(app, path: str) -> tuple[int, dict[str, str], bytes]:
    events: list[dict] = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        events.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8810),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))
    start = next(item for item in events if item["type"] == "http.response.start")
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    body = b"".join(item.get("body", b"") for item in events if item["type"] == "http.response.body")
    return int(start["status"]), headers, body


def test_ocean_owns_root_manifest_worker_and_offline_shell():
    app = OceanOriginApp(_ProviderApp(), prefix="/control", title="OCEAN Full Dev")

    root_status, root_headers, _ = _request(app, "/")
    assert root_status == 307
    assert root_headers["location"] == "/control/"
    assert root_headers["cache-control"] == "no-store"

    manifest_status, manifest_headers, manifest_body = _request(app, "/manifest.webmanifest")
    manifest = json.loads(manifest_body)
    assert manifest_status == 200
    assert manifest_headers["content-type"] == "application/manifest+json; charset=utf-8"
    assert manifest["name"] == "OCEAN Full Dev"
    assert manifest["short_name"] == "OCEAN"
    assert manifest["start_url"] == "/control/"
    assert manifest["scope"] == "/control/"

    worker_status, worker_headers, worker_body = _request(app, "/sw.js")
    worker = worker_body.decode("utf-8")
    assert worker_status == 200
    assert worker_headers["content-type"] == "application/javascript; charset=utf-8"
    assert "registration.unregister" in worker
    assert "caches.keys" in worker
    assert "ellmos-core-pwa" in worker

    offline_status, _, offline_body = _request(app, "/offline")
    offline = offline_body.decode("utf-8")
    assert offline_status == 200
    assert "OCEAN Full Dev ist gerade offline" in offline
    assert "TerminPilot" not in offline


def test_ocean_control_html_evicts_the_legacy_root_worker_and_cache():
    app = OceanOriginApp(_ProviderApp(), prefix="/control", title="OCEAN Full Dev")

    status, headers, body = _request(app, "/control/")
    html = body.decode("utf-8")

    assert status == 200
    assert "provider" in html
    assert "data-ocean-origin-cleanup" in html
    assert "navigator.serviceWorker.getRegistrations" in html
    assert "caches.keys" in html
    assert "ellmos-core-pwa" in html
    assert "TerminPilot" not in html
    assert headers["cache-control"] == "no-store"
    assert int(headers["content-length"]) == len(body)


def test_non_ocean_provider_pages_remain_delegated_without_injection():
    app = OceanOriginApp(_ProviderApp(), prefix="/control", title="OCEAN Full Dev")

    status, _, body = _request(app, "/api/health")

    assert status == 200
    assert b"data-ocean-origin-cleanup" not in body
