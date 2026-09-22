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
import signal
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


STATE_SCHEMA = "ellmos.open-ocean-runtime-state.v1"
ATOMIC_REPLACE_ATTEMPTS = 20
ATOMIC_REPLACE_RETRY_SECONDS = 0.05
POSIX_SIGTERM = getattr(signal, "SIGTERM", 15)
POSIX_SIGKILL = getattr(signal, "SIGKILL", 9)
POSIX_GROUP_POLL_SECONDS = 0.05


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


class ProcessFenceError(RuntimeError):
    """A runtime process group could not be stopped and positively verified."""


def _capture_posix_process_fence(pid: int) -> dict[str, int | str]:
    """Capture the session/process-group identity created for one runtime child."""
    try:
        getpgid = getattr(os, "getpgid")
        getsid = getattr(os, "getsid")
        process_group_id = int(getpgid(pid))
        session_id = int(getsid(pid))
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise ProcessFenceError(
            f"POSIX-Prozessgruppe für Runtime-PID {pid} nicht belegbar."
        ) from exc
    if process_group_id != pid or session_id != pid:
        raise ProcessFenceError(
            f"POSIX-Fence für Runtime-PID {pid} ist nicht an Session-/"
            f"Prozessgruppenführer gebunden (sid={session_id}, pgid={process_group_id})."
        )
    return {
        "kind": "posix-session-group",
        "pgid": process_group_id,
        "sid": session_id,
    }


def _validate_posix_process_fence(
    child: subprocess.Popen[Any],
    process_fence: dict[str, Any],
) -> tuple[int, int]:
    if process_fence.get("kind") != "posix-session-group":
        raise ProcessFenceError("Unbekannter oder fehlender POSIX-Prozessgruppenbeleg.")
    process_group_id = process_fence.get("pgid")
    session_id = process_fence.get("sid")
    if (
        isinstance(process_group_id, bool)
        or not isinstance(process_group_id, int)
        or process_group_id <= 0
        or isinstance(session_id, bool)
        or not isinstance(session_id, int)
        or session_id <= 0
        or process_group_id != child.pid
        or session_id != child.pid
    ):
        raise ProcessFenceError(
            f"Ungültiger POSIX-Prozessgruppenbeleg für Runtime-PID {child.pid}."
        )
    return process_group_id, session_id


def _posix_group_empty(process_group_id: int) -> bool:
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    try:
        killpg(process_group_id, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def _wait_posix_group_empty(process_group_id: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if _posix_group_empty(process_group_id):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(POSIX_GROUP_POLL_SECONDS, remaining))


def _signal_posix_group(process_group_id: int, signum: int) -> bool:
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    try:
        killpg(process_group_id, signum)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


def _wait_child(child: subprocess.Popen[Any], timeout: float) -> bool:
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    except OSError as exc:
        raise ProcessFenceError(f"Runtime-Kind konnte nicht abgefragt werden: {exc}") from exc
    return True


def _terminate_posix_group(
    child: subprocess.Popen[Any],
    process_fence: dict[str, Any],
    timeout: float,
) -> None:
    if timeout <= 0:
        raise ProcessFenceError("POSIX-Stop benötigt ein positives Zeitbudget.")
    process_group_id, _session_id = _validate_posix_process_fence(child, process_fence)
    deadline = time.monotonic() + timeout

    # While the direct child is still alive, refuse to signal if its identity
    # drifted. Once it has exited, the captured group receipt remains the only
    # safe handle to late descendants; the bounded empty-group check prevents
    # reporting success while they remain.
    if child.poll() is None:
        try:
            current_group_id = getattr(os, "getpgid")(child.pid)
            current_session_id = getattr(os, "getsid")(child.pid)
        except (AttributeError, ProcessLookupError):
            pass
        except OSError as exc:
            raise ProcessFenceError(
                f"POSIX-Fence für Runtime-PID {child.pid} nicht erneut prüfbar."
            ) from exc
        else:
            if current_group_id != process_group_id or current_session_id != child.pid:
                raise ProcessFenceError(
                    f"POSIX-Fence für Runtime-PID {child.pid} hat sich verändert."
                )

    if _posix_group_empty(process_group_id):
        return
    if not _signal_posix_group(process_group_id, POSIX_SIGTERM):
        raise ProcessFenceError(
            f"SIGTERM für POSIX-Prozessgruppe {process_group_id} konnte nicht zugestellt werden."
        )
    remaining = max(0.0, deadline - time.monotonic())
    _wait_child(child, remaining)
    if _wait_posix_group_empty(process_group_id, max(0.0, deadline - time.monotonic())):
        return

    if not _signal_posix_group(process_group_id, POSIX_SIGKILL):
        raise ProcessFenceError(
            f"SIGKILL für POSIX-Prozessgruppe {process_group_id} konnte nicht zugestellt werden."
        )
    _wait_child(child, max(0.0, deadline - time.monotonic()))
    if not _wait_posix_group_empty(process_group_id, max(0.0, deadline - time.monotonic())):
        raise ProcessFenceError(
            f"POSIX-Prozessgruppe {process_group_id} blieb nach SIGKILL nicht leer."
        )


def _terminate_unfenced_posix_child(child: subprocess.Popen[Any], timeout: float = 5.0) -> None:
    """Best-effort bootstrap cleanup when the promised fence could not be captured.

    A group signal is used only after the requested new-session invariant is
    independently observed. If that observation is unavailable, direct-child
    cleanup is the only signal that cannot accidentally reach the caller.
    """
    try:
        process_group_id = getattr(os, "getpgid")(child.pid)
        session_id = getattr(os, "getsid")(child.pid)
    except (AttributeError, OSError):
        process_group_id = None
        session_id = None
    if (
        process_group_id == child.pid
        and session_id == child.pid
        and _signal_posix_group(process_group_id, POSIX_SIGKILL)
    ):
        pass
    else:
        try:
            child.kill()
        except OSError:
            pass
    try:
        child.wait(timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _terminate_child(
    child: subprocess.Popen[Any],
    timeout: float = 5.0,
    *,
    process_fence: dict[str, Any] | None = None,
) -> None:
    if os.name != "nt":
        if process_fence is None:
            raise ProcessFenceError(
                "POSIX-Stop ohne Prozessgruppenbeleg verweigert; kein Direkt-Kind-Only-Fallback."
            )
        _terminate_posix_group(child, process_fence, timeout)
        return
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=timeout)


def _handler(
    server: ThreadingHTTPServer,
    token: str,
    child: subprocess.Popen[Any],
    process_fence: dict[str, Any] | None,
):
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
            group_empty = (
                _posix_group_empty(int(process_fence["pgid"]))
                if os.name != "nt" and process_fence is not None
                else returncode is not None
            )
            self._json(200, {
                "status": "stopped" if returncode is not None and group_empty else "running",
                "child_pid": child.pid,
                "returncode": returncode,
                "process_group_empty": group_empty,
            })

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if not self._authorized():
                self._json(403, {"error": "forbidden"})
                return
            if self.path != "/stop":
                self._json(404, {"error": "not-found"})
                return
            try:
                _terminate_child(child, process_fence=process_fence)
            except ProcessFenceError as exc:
                self._json(409, {
                    "status": "stop-failed",
                    "child_pid": child.pid,
                    "error": str(exc),
                })
                return
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
    start_new_session = os.name != "nt"
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    shutdown_requested = False
    previous_sigterm = None

    def request_shutdown(_signum: int, _frame: Any) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True

    if os.name != "nt":
        previous_sigterm = signal.signal(signal.SIGTERM, request_shutdown)

    child: subprocess.Popen[Any] | None = None
    process_fence: dict[str, Any] | None = None
    server: ThreadingHTTPServer | None = None
    state: dict[str, Any] | None = None
    try:
        with log_path.open("ab", buffering=0) as log_handle:
            child = subprocess.Popen(
                [str(item) for item in spec["command"]],
                cwd=spec["cwd"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
            if os.name != "nt":
                process_fence = _capture_posix_process_fence(child.pid)
            server = ThreadingHTTPServer(("127.0.0.1", 0), lambda *args: None)
            server.stop_requested = False
            server.RequestHandlerClass = _handler(server, token, child, process_fence)
            server.timeout = 0.2
            state = {
                "schema": STATE_SCHEMA,
                "instance_id": spec["instance_id"],
                "runtime_id": spec["runtime_id"],
                "status": "running",
                "supervisor_pid": os.getpid(),
                "child_pid": child.pid,
                "process_fence": process_fence,
                "control": {"host": "127.0.0.1", "port": server.server_address[1], "token": token},
                "runtime_url": spec["runtime_url"],
                "health_url": spec["health_url"],
                "started_at": _now(),
            }
            _write_json_atomic(state_path, state)
            while not shutdown_requested and not getattr(server, "stop_requested", False):
                group_empty = (
                    _posix_group_empty(int(process_fence["pgid"]))
                    if os.name != "nt" and process_fence is not None
                    else True
                )
                if child.poll() is not None and group_empty:
                    break
                server.handle_request()
    finally:
        if server is not None:
            server.server_close()
        cleanup_error: ProcessFenceError | None = None
        if child is not None:
            try:
                if os.name != "nt" and process_fence is None:
                    _terminate_unfenced_posix_child(child)
                else:
                    _terminate_child(child, process_fence=process_fence)
            except ProcessFenceError as exc:
                cleanup_error = exc
                if state is not None:
                    state.update({
                        "status": "stop-failed",
                        "returncode": child.poll(),
                        "stop_error": str(exc),
                        "stopped_at": _now(),
                    })
                    _write_json_atomic(state_path, state)
            else:
                if state is not None:
                    state.update({"status": "stopped", "returncode": child.poll(), "stopped_at": _now()})
                    _write_json_atomic(state_path, state)
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        if cleanup_error is not None:
            raise cleanup_error
    return int(child.returncode if child is not None and child.returncode is not None else 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args(argv)
    return supervise(args.spec)


if __name__ == "__main__":
    raise SystemExit(main())
