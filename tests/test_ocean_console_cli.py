"""Tests for OCEAN API Client and Console CLI (tools/ocean_api_client.py, tools/ocean_console.py, ocean.py)."""

from __future__ import annotations

import argparse
import http.server
import json
import sys
import threading
from typing import Any
from unittest.mock import patch

import pytest

from tools.ocean_api_client import (
    OceanApiClient,
    OceanApiError,
    resolve_base_url,
    resolve_token,
)
from tools.ocean_console import handle_chat


class MockOceanHttpHandler(http.server.BaseHTTPRequestHandler):
    """Mock server implementing the OCEAN / BACH Runtime API endpoints."""

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Silent during tests

    def do_GET(self) -> None:
        url_parts = self.path.split("?")
        path = url_parts[0]

        if path == "/api/system/core-agents":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "schema": "bach.core-system-agents.v1",
                "agents": [
                    {
                        "id": "buddha_chat",
                        "name": "Buddha Chat",
                        "status": "ready",
                        "model": "qwen3.8:27b-mlx",
                        "current_activity": "Bereit",
                        "runtime_verified": True,
                    },
                    {
                        "id": "buddha_boss",
                        "name": "Boss · Koordination",
                        "status": "paused",
                        "auto_paused": True,
                        "model": "qwen3.8:27b-mlx",
                        "current_activity": "Pausiert",
                        "runtime_verified": True,
                    },
                ],
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/system/workers":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = [
                {
                    "id": "worker-1234",
                    "name": "Cloud Worker",
                    "status": "running",
                    "running": True,
                    "model": "glm-5.3:cloud",
                    "current_activity": "Verarbeite Task #42",
                    "runtime_verified": True,
                },
                {
                    "id": "worker-err1",
                    "name": "Error Worker",
                    "status": "error",
                    "last_error": "Backend timeout",
                    "model": "openrouter/free",
                    "current_activity": "Fehler aufgetreten",
                    "runtime_verified": False,
                },
            ]
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/agent-history/sessions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "schema": "bach.agent-history.v1",
                "total": 1,
                "sessions": [
                    {
                        "id": 1001,
                        "name": "Chat (buddha_chat)",
                        "created_at": "2026-11-09T12:00:00Z",
                        "source": "user",
                        "stored_message_count": 4,
                        "chat_id": "slot:buddha_chat:abc123",
                    }
                ],
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/agent-history/sessions/1001":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "snapshot_id": 1001,
                "name": "Chat (buddha_chat)",
                "created_at": "2026-11-09T12:00:00Z",
                "chat_id": "slot:buddha_chat:abc123",
                "messages": [
                    {"role": "user", "content": "Hallo"},
                    {"role": "assistant", "content": "Guten Tag! Wie kann ich helfen?"},
                    {"role": "tool", "name": "read_file", "content": "content of file"},
                ],
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/tasks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "tasks": [
                    {
                        "id": 42,
                        "title": "Dokumentation renovieren",
                        "status": "open",
                        "priority": "high",
                        "assigned_to": "buddha_developer",
                    }
                ]
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/tasks/42":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "id": 42,
                "title": "Dokumentation renovieren",
                "status": "open",
                "priority": "high",
                "assigned_to": "buddha_developer",
                "description": "Ausführliche Beschreibung für Task 42",
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/tasks/42/history":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "events": [
                    {"timestamp": "2026-11-09T10:00:00Z", "action": "created", "note": "Angelegt"}
                ]
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/task-returns/timeline":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "schema": "task-returns.timeline.v1",
                "total": 1,
                "events": [
                    {
                        "task_id": 42,
                        "reason": "lease_timeout",
                        "worker_id": "worker-1234",
                        "created_at": "2026-11-09T11:00:00Z",
                    }
                ],
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')

    def do_POST(self) -> None:
        url_parts = self.path.split("?")
        path = url_parts[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = {}

        if path == "/api/system/core-agents/buddha_chat/toggle":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "enabled": body.get("enabled", True)}).encode("utf-8"))
            return

        if path == "/api/system/workers/worker-1234/stop":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"success": true, "status": "stopped"}')
            return

        if path == "/api/system/workers/worker-1234/start":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"success": true, "status": "started"}')
            return

        if path == "/api/agent-history/sessions/1001/resume":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"resumed": True, "worker": body.get("worker_id")}).encode("utf-8"))
            return

        if path == "/api/chat-control/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            reply = f"Antwort auf: {body.get('prompt')}"
            self.wfile.write(json.dumps({"reply": reply, "chat_id": body.get("chat_id")}).encode("utf-8"))
            return

        if path == "/api/chat-control/fork":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"chat_id": "slot:buddha_chat:forked12345"}')
            return

        if path == "/api/chat-control/chat/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            # Send SSE events
            events = [
                'data: {"type": "token", "token": "Hallo "}\n\n',
                'data: {"type": "token", "token": "Welt!"}\n\n',
                'data: {"type": "done", "response": {"reply": "Hallo Welt!"}}\n\n',
            ]
            for ev in events:
                self.wfile.write(ev.encode("utf-8"))
                self.wfile.flush()
            return

        if path == "/api/tasks/42/assign":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"assigned": True, "agent": body.get("agent_id")}).encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')


@pytest.fixture(scope="module")
def mock_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), MockOceanHttpHandler)
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield base_url
    server.shutdown()
    server.server_close()


# =============================================================================
# URL & Token Resolution Tests
# =============================================================================

def test_resolve_base_url_explicit():
    assert resolve_base_url(url="http://example.com:8888/") == "http://example.com:8888"


def test_resolve_base_url_env(monkeypatch):
    monkeypatch.setenv("OCEAN_API_URL", "http://env-host:9999")
    assert resolve_base_url() == "http://env-host:9999"


def test_resolve_base_url_workspace(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "runtime.json").write_text(json.dumps({"url": "http://workspace-host:8810"}), encoding="utf-8")
    assert resolve_base_url(workspace=tmp_path) == "http://workspace-host:8810"


def test_resolve_token_explicit():
    assert resolve_token("explicit-secret") == "explicit-secret"


def test_resolve_token_env(monkeypatch):
    monkeypatch.setenv("OCEAN_API_TOKEN", "token-from-ocean-env")
    assert resolve_token() == "token-from-ocean-env"


def test_resolve_token_file(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEAN_API_TOKEN", raising=False)
    monkeypatch.delenv("BACH_CONTROL_API_TOKEN", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    ocean_dir = fake_home / ".ocean"
    ocean_dir.mkdir()
    (ocean_dir / "device_token").write_text("file-secret-token\n", encoding="utf-8")

    with patch("pathlib.Path.home", return_value=fake_home):
        assert resolve_token() == "file-secret-token"


# =============================================================================
# OceanApiClient Method Tests
# =============================================================================

def test_client_list_agents(mock_server):
    client = OceanApiClient(base_url=mock_server, token="test-tok")
    agents = client.list_agents()
    assert len(agents) == 4

    groups = {a["id"]: a["status_group"] for a in agents}
    assert groups["buddha_chat"] == "ready"
    assert groups["buddha_boss"] == "paused"
    assert groups["worker-1234"] == "running"
    assert groups["worker-err1"] == "error"

    ready_only = client.list_agents(status_filter="ready")
    assert len(ready_only) == 1
    assert ready_only[0]["id"] == "buddha_chat"


def test_client_show_agent(mock_server):
    client = OceanApiClient(base_url=mock_server)
    agent = client.show_agent("buddha_chat")
    assert agent["name"] == "Buddha Chat"
    assert agent["kind"] == "core"

    with pytest.raises(OceanApiError) as exc_info:
        client.show_agent("nonexistent_agent")
    assert exc_info.value.status_code == 404


def test_client_control_agent(mock_server):
    client = OceanApiClient(base_url=mock_server)
    # Core agent start
    res_core = client.control_agent("buddha_chat", "start")
    assert res_core.get("success") is True

    # Worker stop
    res_worker = client.control_agent("worker-1234", "stop")
    assert res_worker.get("status") == "stopped"

    with pytest.raises(OceanApiError):
        client.control_agent("buddha_chat", "invalid_action")


def test_client_sessions(mock_server):
    client = OceanApiClient(base_url=mock_server)
    sess_list = client.list_sessions(limit=5)
    assert sess_list["total"] == 1
    assert len(sess_list["sessions"]) == 1

    detail = client.show_session(1001, include_tools=True)
    assert detail["snapshot_id"] == 1001
    assert len(detail["messages"]) == 3

    resumed = client.resume_session(1001, worker_id="worker-1234", prompt="weitermachen")
    assert resumed.get("resumed") is True


def test_client_chat_and_fork(mock_server):
    client = OceanApiClient(base_url=mock_server)
    chat_res = client.send_chat("buddha_chat", "Testfrage")
    assert "Antwort auf: Testfrage" in chat_res["reply"]

    fork_res = client.fork_session(1001)
    assert fork_res["chat_id"] == "slot:buddha_chat:forked12345"

    chunks = list(client.stream_chat("buddha_chat", "Test"))
    assert len(chunks) == 3
    assert chunks[0]["token"] == "Hallo "


def test_client_tasks(mock_server):
    client = OceanApiClient(base_url=mock_server)
    tasks = client.list_tasks()
    assert len(tasks["tasks"]) == 1
    assert tasks["tasks"][0]["id"] == 42

    detail = client.show_task(42, history=True)
    assert detail["id"] == 42
    assert "history_events" in detail

    assign_res = client.assign_task(42, agent_id="buddha_developer")
    assert assign_res["assigned"] is True

    returns = client.list_task_returns(hours=24)
    assert returns["total"] == 1


# =============================================================================
# CLI Subcommand Tests via ocean.py / console handlers
# =============================================================================

def test_cli_agents_list(mock_server, capsys):
    from ocean import main

    test_args = ["ocean.py", "agents", "list", "--url", mock_server, "--json"]
    with patch.object(sys, "argv", test_args):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 4


def test_cli_agents_show(mock_server, capsys):
    from ocean import main

    test_args = ["ocean.py", "agents", "show", "buddha_chat", "--url", mock_server, "--json"]
    with patch.object(sys, "argv", test_args):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["id"] == "buddha_chat"


def test_cli_sessions_list(mock_server, capsys):
    from ocean import main

    test_args = ["ocean.py", "sessions", "list", "--url", mock_server, "--json"]
    with patch.object(sys, "argv", test_args):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data["sessions"]) == 1


def test_cli_sessions_show(mock_server, capsys):
    from ocean import main

    test_args = ["ocean.py", "sessions", "show", "1001", "--tools", "--url", mock_server, "--json"]
    with patch.object(sys, "argv", test_args):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["snapshot_id"] == 1001


def test_cli_chat_once(mock_server, capsys):
    from ocean import main

    test_args = [
        "ocean.py",
        "chat",
        "--agent",
        "buddha_chat",
        "--once",
        "Wie spät ist es?",
        "--url",
        mock_server,
        "--json",
    ]
    with patch.object(sys, "argv", test_args):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "Antwort auf: Wie spät ist es?" in data["reply"]


def test_cli_console_once(mock_server, capsys):
    from ocean import main

    test_args = [
        "ocean.py",
        "console",
        "--once",
        "Ping",
        "--url",
        mock_server,
    ]
    with patch.object(sys, "argv", test_args):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        assert "Antwort auf: Ping" in captured.out


def test_cli_tasks_all(mock_server, capsys):
    from ocean import main

    # 1. list
    with patch.object(sys, "argv", ["ocean.py", "tasks", "list", "--url", mock_server, "--json"]):
        assert main() == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data["tasks"]) == 1

    # 2. show
    with patch.object(sys, "argv", ["ocean.py", "tasks", "show", "42", "--url", mock_server, "--json"]):
        assert main() == 0
        data = json.loads(capsys.readouterr().out)
        assert data["id"] == 42

    # 3. assign
    with patch.object(sys, "argv", ["ocean.py", "tasks", "assign", "42", "--agent", "buddha_chat", "--url", mock_server, "--json"]):
        assert main() == 0
        data = json.loads(capsys.readouterr().out)
        assert data["assigned"] is True

    # 4. returns
    with patch.object(sys, "argv", ["ocean.py", "tasks", "returns", "--hours", "24", "--url", mock_server, "--json"]):
        assert main() == 0
        data = json.loads(capsys.readouterr().out)
        assert data["total"] == 1


def test_repl_slash_commands(mock_server):
    """Test interactive REPL input loop handling slash commands."""
    client = OceanApiClient(base_url=mock_server)
    args = argparse.Namespace(
        agent="buddha_chat",
        session=None,
        once=None,
        tools=False,
        stream=False,
        json=False,
    )

    inputs = iter([
        "/help",
        "/status",
        "/new",
        "/tools on",
        "/sessions 5",
        "/load 1001",
        "/fork 1001",
        "/agent buddha_boss",
        "/exit",
    ])

    with patch("builtins.input", side_effect=lambda _: next(inputs)):
        ret = handle_chat(client, args)
        assert ret == 0
