# SPDX-License-Identifier: MIT
"""Tests for PB-11 Option (a) thin Ocean GUI read-route adapters (T-20261107-565575838)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.gui_bridge import bridge_from_workspace, mount_gui_bridge
from tools.gui_server import OceanGuiApp

COMMIT = "b" * 40


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_archive_and_pin(root: Path) -> tuple[Path, Path]:
    files = {
        "index.html": b"<!doctype html><html><title>Ocean</title></html>",
        "tasks/index.html": b"<!doctype html><html><title>Tasks</title></html>",
    }
    manifest = {
        "schema": "ellmos-system-gui.dist.v1",
        "source_commit": COMMIT,
        "files": {k: _digest(v) for k, v in files.items()},
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
    archive = root / "gui.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        for name, blob in files.items():
            zf.writestr("dist/" + name, blob)
        zf.writestr("dist/dist-manifest.json", manifest_bytes)
        zf.writestr("LICENSE", b"MIT\n")
    pin = {
        "schema": "ellmos.open-ocean.gui-consumer.v1",
        "id": "ellmos-system-gui",
        "version": "0.2.40",
        "status": "pinned_artifact_only",
        "activation_ready": False,
        "source": {
            "repository": "ellmos-ai/ellmos-system-gui",
            "commit": COMMIT,
            "archive_sha256": _digest(archive.read_bytes()),
            "dist_manifest_schema": "ellmos-system-gui.dist.v1",
        },
        "required_backend_routes": [
            "/api/gui/brand",
            "/api/gui/backend-origin",
            "/api/gui/capabilities",
        ],
    }
    pin_path = root / "pin.json"
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    return archive, pin_path


def _seed_taskplan_db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE rinnsal_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT DEFAULT 'P2',
                agent_id TEXT DEFAULT 'default',
                assigned_to TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                done_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO rinnsal_tasks (title, description, status, priority, assigned_to, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Thin GUI Adapter verdrahten", "PB-11 Option a", "open", "P1", "user", "ocean;pb11", "2026-11-22T10:00:00Z"),
        )
        conn.execute(
            "INSERT INTO rinnsal_tasks (title, description, status, priority, assigned_to, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Worker Lauf prüfen", "Hintergrundtest", "active", "P2", "codex", "worker", "2026-11-22T11:00:00Z"),
        )
        conn.execute(
            "INSERT INTO rinnsal_tasks (title, description, status, priority, assigned_to, tags, done_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Altaufgabe erledigt", "Fertig", "done", "P3", "", "archive", "2026-11-21T12:00:00Z"),
        )
    return path


def _seed_notes_db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE note_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT DEFAULT 'note',
                title TEXT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'note',
                tags TEXT,
                is_archived INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO note_entries (entry_type, title, content, category, tags, is_archived, created_at) "
            "VALUES ('note', 'Architektur-Impuls', 'Dünne Adapter statt Kopie', 'architektur', 'pb11,ocean', 0, '2026-11-22 14:00')"
        )
        conn.execute(
            "INSERT INTO note_entries (entry_type, title, content, category, tags, is_archived, created_at) "
            "VALUES ('logbook', 'Tageslog', 'Katalog auf 92 Module gebracht', 'log', 'sync', 0, '2026-11-22 15:00')"
        )
        conn.execute(
            "INSERT INTO note_entries (entry_type, title, content, category, tags, is_archived, created_at) "
            "VALUES ('note', 'Archiviert', 'Soll nicht erscheinen', 'note', '', 1, '2026-11-20 09:00')"
        )
    return path


def _seed_lock_cache(path: Path) -> Path:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(
        "<!-- AUTO-GENERATED by lock_scan.py --write-cache. DO NOT edit manually. -->\n\n"
        "# LOCK-CACHE\n\n"
        f"As of: {now}\n\n"
        "Active locks: 0\n\n"
        "| Path | scope | owner | created | expires |\n"
        "|---|---|---|---|---|\n"
        "| _(no active locks)_ | | | | |\n",
        encoding="utf-8",
    )
    return path


async def _asgi_get(app, path: str, query: str = "", method: str = "GET") -> tuple[int, dict | bytes]:
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        messages.append(msg)

    await app(
        {"type": "http", "path": path, "query_string": query.encode("latin-1"), "method": method},
        receive,
        send,
    )
    status = messages[0]["status"]
    raw = b"".join(m.get("body", b"") for m in messages[1:])
    try:
        return status, json.loads(raw.decode("utf-8"))
    except ValueError:
        return status, raw


def test_ocean_gui_app_serves_all_five_pb11_core_read_families_and_keeps_writes_405(tmp_path):
    archive, pin = _make_archive_and_pin(tmp_path)
    ws = tmp_path / "workspace"
    (ws / "modules").mkdir(parents=True)
    (ws / "skills").mkdir(parents=True)
    _seed_taskplan_db(ws / "taskplan.db")
    _seed_notes_db(ws / "notes.db")
    lock_cache = _seed_lock_cache(tmp_path / "LOCK-CACHE.md")
    assignees = tmp_path / "slots.json"
    assignees.write_text(
        json.dumps({"slots": [{"id": "codex_worker", "name": "Codex", "backend": "codex", "enabled": True, "runtime_verified": True, "living": True}]}),
        encoding="utf-8",
    )
    (ws / "ocean.gui-bridge.json").write_text(
        json.dumps({
            "schema": "ellmos.open-ocean.gui-bridge.v1",
            "lock_cache": str(lock_cache),
            "task_db": str(ws / "taskplan.db"),
            "notes_db": str(ws / "notes.db"),
            "task_assignees_config": str(assignees),
        }),
        encoding="utf-8",
    )

    app = OceanGuiApp(archive, pin_path=pin, workspace=ws)

    # 1. Tasks (readTaskPage contract: nonterminal, comma status, q, assignment_group, detail, result, assignees)
    st, data = asyncio.run(_asgi_get(app, "/api/tasks", "status=nonterminal&assignment_group=all&limit=10&offset=0"))
    assert st == 200 and data["success"] is True
    assert data["total"] == 2 and data["has_more"] is False
    assert {t["status"] for t in data["tasks"]} == {"pending", "in_progress"}
    assert data["applied_filters"] == {"status": "nonterminal", "assignment_group": "all"}

    st_ov, ov = asyncio.run(_asgi_get(app, "/api/tasks", "status=pending,in_progress&limit=5"))
    assert st_ov == 200 and ov["total"] == 2

    st_u, user_tasks = asyncio.run(_asgi_get(app, "/api/tasks", "status=nonterminal&assignment_group=user&q=Adapter"))
    assert st_u == 200 and user_tasks["total"] == 1
    assert user_tasks["applied_filters"]["q"] == "Adapter"
    assert user_tasks["tasks"][0]["title"] == "Thin GUI Adapter verdrahten"

    st_d, detail = asyncio.run(_asgi_get(app, "/api/tasks/1"))
    assert st_d == 200 and detail["success"] is True and detail["task"]["id"] == 1

    st_r, res = asyncio.run(_asgi_get(app, "/api/tasks/3/result"))
    assert st_r == 200 and res["found"] is True and res["status"] == "done"

    st_a, ta = asyncio.run(_asgi_get(app, "/api/task-assignees"))
    assert st_a == 200 and ta["schema"] == "bach.task-assignees.v1" and len(ta["targets"]) == 1

    # 2. Governance
    st_lk, lk = asyncio.run(_asgi_get(app, "/api/governance/locks"))
    assert st_lk == 200 and lk["availability"] == "available" and lk["count"] == 0
    st_gs, gs = asyncio.run(_asgi_get(app, "/api/governance/status"))
    assert st_gs == 200 and gs["status"] == "observed"

    # 3. Capabilities
    st_sk, sk = asyncio.run(_asgi_get(app, "/api/capabilities/skills/library"))
    assert st_sk == 200 and "skills" in sk

    # 4. Blueprints & Agent Library
    st_bp, bp = asyncio.run(_asgi_get(app, "/api/agent-studio/blueprints"))
    assert st_bp == 200 and bp["success"] is True and len(bp["templates"]) >= 6
    st_lib, lib = asyncio.run(_asgi_get(app, "/api/agenten/library"))
    assert st_lib == 200 and lib["schema"] == "ellmos.agent-library.v1"
    assert "provider_sockets" in lib["role_socket_catalog"]

    # 5. Notes / Denkarium (excludes archived, supports kind & search)
    st_n, notes = asyncio.run(_asgi_get(app, "/api/notes"))
    assert st_n == 200 and notes["success"] is True and notes["count"] == 2
    st_dk, log_notes = asyncio.run(_asgi_get(app, "/api/denkarium", "kind=logbuch"))
    assert st_dk == 200 and log_notes["count"] == 1 and log_notes["notes"][0]["kind"] == "logbuch"

    # Capabilities report reflects truthful availability & keeps writes rejected (405)
    st_cap, cap = asyncio.run(_asgi_get(app, "/api/gui/capabilities"))
    assert st_cap == 200
    by_ep = {(e["method"], e["path"]): e for e in cap["endpoints"]}
    for path in ("/api/tasks", "/api/agent-studio/blueprints", "/api/agenten/library", "/api/notes", "/api/governance/locks"):
        assert by_ep[("GET", path)]["available"] is True
    assert by_ep[("POST", "/api/tasks")]["available"] is False

    st_post, _ = asyncio.run(_asgi_get(app, "/api/tasks", method="POST"))
    assert st_post == 405


def test_mount_gui_bridge_serves_new_read_routes_behind_auth(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed_taskplan_db(ws / "taskplan.db")
    _seed_notes_db(ws / "notes.db")
    bridge = bridge_from_workspace(ws)

    app = FastAPI()

    def auth(request):
        if request.headers.get("x-session") != "ok":
            raise HTTPException(401, "unauthorized")

    mount_gui_bridge(app, bridge, auth, auth)
    client = TestClient(app, follow_redirects=False)

    for route in ("/api/tasks", "/api/tasks/1", "/api/agent-studio/blueprints", "/api/agenten/library", "/api/notes", "/api/denkarium"):
        assert client.get(route).status_code == 401
        resp = client.get(route, headers={"x-session": "ok"})
        assert resp.status_code == 200, f"{route} -> {resp.status_code} {resp.text}"
