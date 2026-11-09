"""OCEAN API Client.

Dual API + CLI Client for the OCEAN / BACH Runtime Server.
Uses only the Python standard library (urllib, json, os, pathlib) with zero
external mandatory dependencies.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Iterable


DEFAULT_OCEAN_PORT = 8810
DEFAULT_BACH_PORT = 8000
DEFAULT_TIMEOUT = 15.0

PROBE_CANDIDATE_URLS = [
    f"http://127.0.0.1:{DEFAULT_OCEAN_PORT}",
    f"http://127.0.0.1:{DEFAULT_BACH_PORT}",
    "http://100.119.69.90:8000",
    "http://100.119.166.96:8000",
    "http://mac-studio:8000",
]


class OceanApiError(Exception):
    """Exception raised when an OCEAN API call fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        url: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.url = url
        self.details = details

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"(HTTP {self.status_code})")
        if self.url:
            parts.append(f"[{self.url}]")
        return " ".join(parts)


def resolve_base_url(
    url: str | None = None,
    workspace: str | Path | None = None,
    probe_candidates: Iterable[str] | None = None,
    probe_timeout: float = 0.5,
) -> str:
    """Deterministically resolve the OCEAN API base URL.

    Resolution order:
    1. Explicit url argument
    2. Environment variable OCEAN_API_URL
    3. Workspace runtime state: <workspace>/state/runtime.json
    4. Live probe on default loopback and tailscale candidates
    5. Fallback: http://127.0.0.1:8810
    """
    if url:
        return url.rstrip("/")

    env_url = os.environ.get("OCEAN_API_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")

    if workspace:
        ws_path = Path(workspace).expanduser().resolve()
        runtime_state = ws_path / "state" / "runtime.json"
        if runtime_state.is_file():
            try:
                state_data = json.loads(runtime_state.read_text(encoding="utf-8"))
                if isinstance(state_data, dict):
                    if state_data.get("url"):
                        return str(state_data["url"]).rstrip("/")
                    if state_data.get("port"):
                        host = state_data.get("host") or "127.0.0.1"
                        return f"http://{host}:{state_data['port']}"
            except (OSError, json.JSONDecodeError):
                pass

    candidates = list(probe_candidates) if probe_candidates is not None else PROBE_CANDIDATE_URLS
    for candidate in candidates:
        candidate_clean = candidate.rstrip("/")
        test_url = f"{candidate_clean}/api/system/core-agents"
        req = urllib.request.Request(
            test_url,
            headers={"User-Agent": "ocean-api-probe/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=probe_timeout) as resp:
                if resp.status in (200, 204):
                    return candidate_clean
        except urllib.error.HTTPError as err:
            # 401 or 403 means the server is actively running and listening!
            if err.code in (401, 403, 200, 404):
                return candidate_clean
        except (urllib.error.URLError, OSError, TimeoutError):
            continue

    return f"http://127.0.0.1:{DEFAULT_OCEAN_PORT}"


def resolve_token(token: str | None = None) -> str | None:
    """Deterministically resolve the device/control API auth token.

    Resolution order:
    1. Explicit token argument
    2. Environment variable OCEAN_API_TOKEN
    3. Environment variable BACH_CONTROL_API_TOKEN
    4. ~/.ocean/device_token
    5. ~/.bach/gui_auth_token
    6. ~/.credentials/bach_control_api_token
    7. ~/.bach/control_api_token
    """
    if token and str(token).strip():
        return str(token).strip()

    for env_var in ("OCEAN_API_TOKEN", "BACH_CONTROL_API_TOKEN"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    home = Path.home()
    candidate_paths = [
        home / ".ocean" / "device_token",
        home / ".bach" / "gui_auth_token",
        home / ".credentials" / "bach_control_api_token",
        home / ".bach" / "control_api_token",
    ]

    for p in candidate_paths:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except OSError:
                continue

    return None


@dataclass
class AgentSummary:
    """Normalized agent / worker representation."""

    id: str
    name: str
    kind: str  # "core" or "worker"
    status_group: str  # "ready", "running", "paused", "error"
    raw_status: str
    model: str
    activity: str
    runtime_verified: bool
    raw_data: dict[str, Any]


class OceanApiClient:
    """HTTP client for the OCEAN / BACH Runtime API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        workspace: str | Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = resolve_base_url(url=base_url, workspace=workspace)
        self.token = resolve_token(token)
        self.timeout = timeout

    def _headers(self, custom_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "ocean-cli/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-BACH-Device-Token"] = self.token
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        stream: bool = False,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                url = f"{url}?{urllib.parse.urlencode(filtered_params)}"

        data_bytes = None
        req_headers = self._headers(headers)
        if body is not None:
            data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url=url,
            data=data_bytes,
            headers=req_headers,
            method=method.upper(),
        )

        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            if stream:
                return resp
            with resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                try:
                    return json.loads(resp_bytes.decode("utf-8"))
                except json.JSONDecodeError:
                    return resp_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            err_details: Any = err_body
            try:
                err_details = json.loads(err_body)
            except json.JSONDecodeError:
                pass
            msg = f"API-Anfrage fehlgeschlagen: {method} {path}"
            if isinstance(err_details, dict) and "error" in err_details:
                msg = f"{msg} -> {err_details['error']}"
            elif isinstance(err_details, dict) and "detail" in err_details:
                msg = f"{msg} -> {err_details['detail']}"
            raise OceanApiError(
                message=msg,
                status_code=exc.code,
                url=url,
                details=err_details,
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise OceanApiError(
                message=f"Verbindungsfehler zu {url}: {exc}",
                url=url,
            ) from exc

    # =========================================================================
    # Agents & Workers
    # =========================================================================

    @staticmethod
    def _normalize_agent_status(item: dict[str, Any], is_core: bool) -> str:
        """Categorize into ready, running, paused, error."""
        status = str(item.get("status", "")).lower()
        if status in ("error", "failed", "crash"):
            return "error"
        if item.get("last_error") or item.get("error"):
            return "error"

        # Worker specific status checks
        if not is_core:
            queue_status = item.get("queue_status")
            if isinstance(queue_status, dict) and queue_status.get("state") == "error":
                return "error"

        if (
            item.get("running")
            or item.get("worker_active")
            or status in ("running", "busy", "acquired", "in_progress", "active")
        ):
            return "running"

        pause_info = item.get("pause_info")
        is_paused = (
            item.get("auto_paused")
            or (isinstance(pause_info, dict) and pause_info.get("is_paused"))
            or status in ("paused", "hold", "idle_pause")
        )
        if is_paused:
            return "paused"

        return "ready"

    def list_agents(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        """List both core agents and background workers grouped and normalized.

        Status groups: ready, running, paused, error.
        """
        results: list[dict[str, Any]] = []

        # 1. Core Agents
        try:
            core_resp = self._request("GET", "/api/system/core-agents")
            raw_cores = core_resp.get("agents", []) if isinstance(core_resp, dict) else core_resp
            if isinstance(raw_cores, list):
                for agent in raw_cores:
                    if not isinstance(agent, dict):
                        continue
                    group = self._normalize_agent_status(agent, is_core=True)
                    summary = {
                        "id": agent.get("id", ""),
                        "name": agent.get("name", agent.get("id", "")),
                        "kind": "core",
                        "status_group": group,
                        "raw_status": agent.get("status", "ready"),
                        "model": agent.get("resolved_model") or agent.get("model", ""),
                        "activity": agent.get("current_activity", ""),
                        "runtime_verified": bool(agent.get("runtime_verified", False)),
                        "raw": agent,
                    }
                    if not status_filter or group == status_filter.lower():
                        results.append(summary)
        except OceanApiError:
            pass

        # 2. Workers
        try:
            worker_resp = self._request("GET", "/api/system/workers")
            raw_workers = (
                worker_resp.get("workers", [])
                if isinstance(worker_resp, dict)
                else worker_resp
            )
            if isinstance(raw_workers, list):
                for worker in raw_workers:
                    if not isinstance(worker, dict):
                        continue
                    group = self._normalize_agent_status(worker, is_core=False)
                    summary = {
                        "id": worker.get("id", ""),
                        "name": worker.get("name", worker.get("id", "")),
                        "kind": "worker",
                        "status_group": group,
                        "raw_status": worker.get("status", "idle"),
                        "model": worker.get("resolved_model") or worker.get("model", ""),
                        "activity": worker.get("current_activity", ""),
                        "runtime_verified": bool(worker.get("runtime_verified", False)),
                        "raw": worker,
                    }
                    if not status_filter or group == status_filter.lower():
                        results.append(summary)
        except OceanApiError:
            pass

        return results

    def show_agent(self, agent_id: str) -> dict[str, Any]:
        """Get detail information for an agent or worker."""
        agents = self.list_agents()
        for a in agents:
            if a["id"] == agent_id:
                return a
        raise OceanApiError(f"Agent oder Worker '{agent_id}' wurde nicht gefunden.", status_code=404)

    def control_agent(self, agent_id: str, action: str) -> dict[str, Any]:
        """Control agent/worker (start, resume, pause, stop)."""
        action = action.lower()
        if action not in ("start", "resume", "pause", "stop"):
            raise OceanApiError(f"Ungültige Aktion '{action}'. Gültig sind: start, resume, pause, stop.")

        agent_info = self.show_agent(agent_id)
        is_core = agent_info["kind"] == "core"

        if is_core:
            # Core agent toggle
            enable = action in ("start", "resume")
            return self._request(
                "POST",
                f"/api/system/core-agents/{agent_id}/toggle",
                body={"enabled": enable},
            )

        # Worker control
        # map resume -> start if worker endpoint expects start
        mapped_action = action
        return self._request(
            "POST",
            f"/api/system/workers/{agent_id}/{mapped_action}",
            body={},
        )

    # =========================================================================
    # Sessions
    # =========================================================================

    def list_sessions(
        self,
        agent: str | None = None,
        source: str | None = None,
        problems: bool = False,
        limit: int = 25,
    ) -> dict[str, Any]:
        """List sessions from /api/agent-history/sessions."""
        params: dict[str, Any] = {
            "limit": limit,
        }
        if agent:
            params["slot_id"] = agent
        if source:
            params["source"] = source
        if problems:
            params["problems"] = "true"

        return self._request("GET", "/api/agent-history/sessions", params=params)

    def show_session(self, snapshot_id: int | str, include_tools: bool = False) -> dict[str, Any]:
        """Get session snapshot transcript."""
        params = {"include_tools": "true" if include_tools else "false"}
        return self._request("GET", f"/api/agent-history/sessions/{snapshot_id}", params=params)

    def resume_session(
        self,
        snapshot_id: int | str,
        worker_id: str,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Resume a session via /api/agent-history/sessions/{snapshot_id}/resume."""
        body = {
            "worker_id": worker_id,
            "prompt": prompt or "",
        }
        return self._request("POST", f"/api/agent-history/sessions/{snapshot_id}/resume", body=body)

    # =========================================================================
    # Chat & Interactive Console
    # =========================================================================

    def send_chat(
        self,
        agent_id: str,
        prompt: str,
        chat_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat message to /api/chat-control/chat."""
        cid = chat_id or f"slot:{agent_id}:{secrets.token_hex(16)}"
        body = {
            "prompt": prompt,
            "chat_id": cid,
            "agent_id": agent_id,
        }
        return self._request("POST", "/api/chat-control/chat", body=body)

    def fork_session(
        self,
        snapshot_id: int | str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Fork a session snapshot into a new active chat."""
        body: dict[str, Any] = {
            "snapshot_id": snapshot_id,
        }
        if agent_id:
            body["agent_id"] = agent_id
        return self._request("POST", "/api/chat-control/fork", body=body)

    def stream_chat(
        self,
        agent_id: str,
        prompt: str,
        chat_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream chat tokens / events via SSE. Falls back to send_chat on 404/501."""
        cid = chat_id or f"slot:{agent_id}:{secrets.token_hex(16)}"
        body = {
            "prompt": prompt,
            "chat_id": cid,
            "agent_id": agent_id,
        }
        try:
            resp = self._request(
                "POST",
                "/api/chat-control/chat/stream",
                body=body,
                stream=True,
                headers={"Accept": "text/event-stream"},
            )
            # Read SSE stream
            event_type = "message"
            data_buffer: list[str] = []
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if data_buffer:
                        full_data = "\n".join(data_buffer)
                        data_buffer.clear()
                        try:
                            parsed = json.loads(full_data)
                            if isinstance(parsed, dict):
                                yield parsed
                            else:
                                yield {"type": event_type, "content": parsed}
                        except json.JSONDecodeError:
                            yield {"type": event_type, "content": full_data}
                    event_type = "message"
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_buffer.append(line[5:].strip())
        except OceanApiError as exc:
            # Fallback to standard send_chat
            if exc.status_code in (404, 405, 501):
                res = self.send_chat(agent_id, prompt, chat_id=cid)
                yield {"type": "done", "response": res}
            else:
                raise

    # =========================================================================
    # Tasks
    # =========================================================================

    def list_tasks(
        self,
        status: str | None = None,
        assigned: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List tasks from /api/tasks."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if assigned:
            params["assigned_to"] = assigned
        return self._request("GET", "/api/tasks", params=params)

    def show_task(self, task_id: int | str, history: bool = False) -> dict[str, Any]:
        """Get task detail and optional history."""
        task = self._request("GET", f"/api/tasks/{task_id}")
        if history:
            try:
                hist = self._request("GET", f"/api/tasks/{task_id}/history")
                if isinstance(task, dict):
                    task["history_events"] = hist
            except OceanApiError:
                pass
        return task

    def assign_task(self, task_id: int | str, agent_id: str) -> dict[str, Any]:
        """Assign task to an agent/worker."""
        return self._request("POST", f"/api/tasks/{task_id}/assign", body={"agent_id": agent_id})

    def list_task_returns(
        self,
        hours: int = 24,
        worker: str | None = None,
    ) -> dict[str, Any]:
        """List task returns timeline."""
        try:
            res = self._request("GET", "/api/task-returns/timeline", params={"hours": hours})
            if worker and isinstance(res, dict) and "events" in res:
                res["events"] = [e for e in res["events"] if e.get("worker_id") == worker or e.get("worker") == worker]
            return res
        except OceanApiError:
            return self._request("GET", "/api/system/worker-returns", params={"hours": hours})
