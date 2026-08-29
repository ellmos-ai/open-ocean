#!/usr/bin/env python3
"""Small loopback-only supervisor for one OCEAN runtime process.

The lifecycle CLI never kills a PID from a stale file.  It stops a runtime only
through this per-instance control channel and a random bearer token written into
the private local runtime-state file.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


STATE_SCHEMA = "ellmos.open-ocean-runtime-state.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def _terminate_child(child: subprocess.Popen[Any], timeout: float = 5.0) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=timeout)


def _handler(server: ThreadingHTTPServer, token: str, child: subprocess.Popen[Any]):
    class Handler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {token}"

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if not self._authorized():
                self._json(403, {"error": "forbidden"})
                return
            if self.path != "/status":
                self._json(404, {"error": "not-found"})
                return
            returncode = child.poll()
            self._json(200, {
                "status": "running" if returncode is None else "stopped",
                "child_pid": child.pid,
                "returncode": returncode,
            })

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if not self._authorized():
                self._json(403, {"error": "forbidden"})
                return
            if self.path != "/stop":
                self._json(404, {"error": "not-found"})
                return
            _terminate_child(child)
            setattr(server, "stop_requested", True)
            self._json(200, {"status": "stopped", "child_pid": child.pid})

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def supervise(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema") != "ellmos.open-ocean-runtime-spec.v1":
        raise ValueError("unsupported runtime specification")
    state_path = Path(spec["state_path"])
    log_path = Path(spec["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in (spec.get("env") or {}).items()})
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with log_path.open("ab", buffering=0) as log_handle:
        child = subprocess.Popen(
            [str(item) for item in spec["command"]],
            cwd=spec["cwd"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            creationflags=creationflags,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), lambda *args: None)
        server.RequestHandlerClass = _handler(server, spec["token"], child)
        server.timeout = 0.2
        state = {
            "schema": STATE_SCHEMA,
            "instance_id": spec["instance_id"],
            "runtime_id": spec["runtime_id"],
            "status": "running",
            "supervisor_pid": os.getpid(),
            "child_pid": child.pid,
            "control": {"host": "127.0.0.1", "port": server.server_address[1], "token": spec["token"]},
            "runtime_url": spec["runtime_url"],
            "health_url": spec["health_url"],
            "started_at": _now(),
        }
        _write_json_atomic(state_path, state)
        try:
            while child.poll() is None and not getattr(server, "stop_requested", False):
                server.handle_request()
        finally:
            server.server_close()
            _terminate_child(child)
            state.update({"status": "stopped", "returncode": child.poll(), "stopped_at": _now()})
            _write_json_atomic(state_path, state)
    return int(child.returncode or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args(argv)
    return supervise(args.spec)


if __name__ == "__main__":
    raise SystemExit(main())
