"""Tests for the bound Ocean GUI API adapters (#2075, #2094, #2097, #2098)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.capability_views import software_inventory
from tools import governance_bridge as gov
from tools.gui_bridge import GuiBridge, bridge_from_workspace, mount_gui_bridge

HEADERS = {"x-test-session": "ok"}


def _client(bridge: GuiBridge) -> TestClient:
    app = FastAPI()

    def auth(request):
        if request.headers.get("x-test-session") != "ok":
            raise HTTPException(401, "login")
        return {"id": 1}

    mount_gui_bridge(app, bridge, auth, auth)
    return TestClient(app, follow_redirects=False)


def test_bound_software_inventory_serves_contract(tmp_path: Path):
    sw_dir = tmp_path / "software"
    (sw_dir / "tools" / "alpha-app").mkdir(parents=True)
    releases = sw_dir / "releases.json"
    releases.write_text(json.dumps({
        "projects": [
            {
                "name": "Alpha App",
                "path": "tools/alpha-app",
                "description": "Demo application",
                "version": "1.2.0",
                "lifecycle": "active",
                "targets": [
                    {"type": "github", "platform": "windows", "status": "published", "version": "1.2.0",
                     "release_url": "https://github.com/ellmos-ai/alpha-app/releases/tag/v1.2.0"}
                ],
            }
        ]
    }), encoding="utf-8")

    bridge = GuiBridge(software=lambda: software_inventory(releases_path=releases))
    client = _client(bridge)
    resp = client.get("/api/capabilities/software", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema"] == "bach.capability-inventory.v1"
    assert body["kind"] == "software" and body["catalog"] == "software-applications"
    assert body["count"] == 1
    item = body["items"][0]
    assert item["name"] == "Alpha App" and item["code_present"] is True
    assert item["source"] == "<software>/releases.json"
    caps = {e["path"]: e for e in bridge.capabilities()["endpoints"]}
    assert caps["/api/capabilities/software"]["available"] is True


def test_bound_audit_and_task_result_and_assignees(tmp_path: Path):
    db_path = tmp_path / "taskplan.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT, completed_at TEXT, updated_at TEXT)")
        conn.execute("INSERT INTO tasks VALUES (42, 'Demo Task', 'done', '2026-10-31T20:00:00+00:00', '2026-10-31T20:00:00+00:00')")
        conn.execute("CREATE TABLE task_history (task_id INTEGER, action TEXT, field_changed TEXT, changed_at TEXT)")
        conn.execute("INSERT INTO task_history VALUES (42, 'status_change', 'status', '2026-10-31T20:00:00+00:00')")
        conn.execute(
            "CREATE TABLE task_leases ("
            "lease_id TEXT PRIMARY KEY, task_id INTEGER, worker_id TEXT, worker_host TEXT, status TEXT, "
            "result_summary TEXT, verification_cmd TEXT, verification_exit_code INTEGER, "
            "verification_output TEXT, changed_files_json TEXT, updated_at TEXT)"
        )
        conn.execute(
            "INSERT INTO task_leases VALUES ("
            "'lease-1', 42, 'buddha', 'mac-studio', 'submitted', 'Implemented feature', "
            "'pytest -q', 0, '4 passed', '[\"taskplan/lease.py\"]', '2026-10-31T20:00:00+00:00')"
        )

    slots_cfg = tmp_path / "slots.json"
    slots_cfg.write_text(json.dumps({
        "agents": [
            {"id": "buddha", "name": "Buddha Worker", "execution_kind": "worker", "backend": "ollama",
             "model": "qwen3:32b", "enabled": True, "runtime_verified": True, "living": True, "running": False}
        ]
    }), encoding="utf-8")

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "ocean.gui-bridge.json").write_text(json.dumps({
        "schema": "ellmos.open-ocean.gui-bridge.v1",
        "task_db": str(db_path),
        "task_assignees_config": str(slots_cfg),
    }), encoding="utf-8")

    bridge = bridge_from_workspace(ws)
    client = _client(bridge)

    audit_resp = client.get("/api/governance/audit?limit=10", headers=HEADERS)
    assert audit_resp.status_code == 200
    audit = audit_resp.json()
    assert audit["availability"] == "available" and audit["count"] == 1
    assert audit["events"][0]["task_id"] == 42 and audit["events"][0]["action"] == "status_change"

    ta_resp = client.get("/api/task-assignees", headers=HEADERS)
    assert ta_resp.status_code == 200
    ta = ta_resp.json()
    assert ta["schema"] == "bach.task-assignees.v1" and ta["targets"][0]["assignable"] is True

    res_resp = client.get("/api/tasks/42/result", headers=HEADERS)
    assert res_resp.status_code == 200
    res = res_resp.json()
    assert res["found"] is True and res["lease_submission"]["worker_id"] == "buddha"
    assert res["lease_submission"]["verification_exit_code"] == 0
    assert client.get("/api/tasks/bad/result", headers=HEADERS).status_code == 422
