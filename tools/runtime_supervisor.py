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
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


STATE_SCHEMA = "ellmos.open-ocean-runtime-state.v1"
ATOMIC_REPLACE_ATTEMPTS = 20
ATOMIC_REPLACE_RETRY_SECONDS = 0.05


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _restrict_to_current_user_windows(path: Path) -> None:
    """Fail-closed ACL lockdown for this state file on Windows, where
    chmod() only ever toggles the read-only attribute and grants no real
    access control. Uses the platform's own icacls.exe (no new dependency).
    (T-20260903-113508213 Blocker 1 -- this state file's own docstring above
    already calls it "the private local runtime-state file"; it carries the
    same control.token the spec file used to carry.)"""
    username = os.environ.get("USERNAME")
    if not username:
        raise OSError("cannot restrict private state-file ACL: USERNAME is unavailable")
    try:
        completed = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise OSError(f"cannot restrict private state-file ACL for {path}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        raise OSError(
            f"cannot restrict private state-file ACL for {path}: icacls exited "
            f"{completed.returncode}: {detail}"
        )


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    # Permissions are set AT CREATION via the os.open() mode, not via a
    # chmod() after write_text() already created the file with default
    # permissions -- that used to leave a window where it was briefly
    # world-readable (T-20260903-113508213 Blocker 1).
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        if os.name == "nt":
            _restrict_to_current_user_windows(temporary)
        for attempt in range(ATOMIC_REPLACE_ATTEMPTS):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == ATOMIC_REPLACE_ATTEMPTS - 1:
                    raise
                # Windows can briefly deny replace while the lifecycle process is
                # reading the old state file. Keep the write atomic and bounded.
                time.sleep(ATOMIC_REPLACE_RETRY_SECONDS)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


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
    # The control-channel bearer token is handed to us via the environment,
    # not the spec file (T-20260903-113508213 Blocker 1) -- nothing else
    # ever needs to read it back from disk. Pop it before deriving the
    # child's environment so it doesn't leak into the runtime it has no use
    # for there.
    token = os.environ.get("OCEAN_RUNTIME_TOKEN")
    if not token:
        raise ValueError("OCEAN_RUNTIME_TOKEN is missing from the environment")
    state_path = Path(spec["state_path"])
    log_path = Path(spec["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("OCEAN_RUNTIME_TOKEN", None)
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
        server.RequestHandlerClass = _handler(server, token, child)
        server.timeout = 0.2
        state = {
            "schema": STATE_SCHEMA,
            "instance_id": spec["instance_id"],
            "runtime_id": spec["runtime_id"],
            "status": "running",
            "supervisor_pid": os.getpid(),
            "child_pid": child.pid,
            "control": {"host": "127.0.0.1", "port": server.server_address[1], "token": token},
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
