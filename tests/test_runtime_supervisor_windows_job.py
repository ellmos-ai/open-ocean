"""Windows: descendants of the runtime child die with the supervisor stop (#2088).

``Popen.terminate()`` only ends the direct child on Windows.  The supervisor therefore
starts the child suspended, puts it into a kill-on-close job object and then resumes it.
"""

from __future__ import annotations

import ast
import ctypes
import inspect
import json
import os
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

import tools.runtime_supervisor as runtime_supervisor
import tools.windows_job as windows_job

windows_only = pytest.mark.skipif(os.name != "nt", reason="job objects are a Windows mechanism")

SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_OBJECT_0 = 0


def _wait_for_exit(pid: int, timeout_ms: int) -> bool:
    """Deterministic: block on the process handle instead of polling a pid."""
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.restype = ctypes.c_void_p
    api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = api.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return not windows_job.process_is_alive(pid)  # gone, or the query raises
    try:
        return api.WaitForSingleObject(handle, timeout_ms) == WAIT_OBJECT_0
    finally:
        api.CloseHandle(handle)


def _calls(function, name: str) -> list[ast.Call]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "attr", None) == name or getattr(node.func, "id", None) == name)
    ]


def _position(function, name: str) -> tuple[int, int]:
    """(line, column) of the first call to ``name`` inside ``function``."""
    calls = _calls(function, name)
    assert calls, f"{function.__name__} no longer calls {name}"
    return min((call.lineno, call.col_offset) for call in calls)


def test_the_windows_start_puts_the_child_into_a_job_before_it_runs():
    """Pins the production decision on every platform (read through the AST).

    Compares source positions, not mere presence: spawn < job creation < assignment,
    and in ``assign_and_resume`` the assignment precedes the resume.
    """
    supervise = runtime_supervisor.supervise
    spawn = _position(supervise, "Popen")
    create = _position(supervise, "create_kill_on_close_job")
    assign = _position(supervise, "assign_and_resume")
    assert spawn < create < assign, "job setup no longer follows the spawn in order"

    tree = ast.parse(textwrap.dedent(inspect.getsource(supervise)))
    windows_branches = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.If) and "'nt'" in ast.unparse(node.test) or
        isinstance(node, ast.If) and '"nt"' in ast.unparse(node.test)
    ]
    assert any(
        "CREATE_SUSPENDED" in ast.unparse(node) and "creationflags" in ast.unparse(node)
        for node in windows_branches
    ), "the Windows branch no longer starts the child suspended"

    inner = windows_job.assign_and_resume
    assert _position(inner, "AssignProcessToJobObject") < _position(inner, "NtResumeProcess"), (
        "the child would run before it is in the job"
    )


@windows_only
def test_the_extended_limit_struct_has_the_documented_size():
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(windows_job._ExtendedLimits) == windows_job.EXTENDED_LIMITS_SIZE_64


@windows_only
def test_windows_stop_without_a_job_fails_closed():
    class Live:
        pid = 4242

        def poll(self):
            return None

    with pytest.raises(runtime_supervisor.ProcessFenceError):
        runtime_supervisor._terminate_child(Live())


@windows_only
def test_a_failed_job_assignment_kills_the_unstarted_child_and_fails_closed(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema": "ellmos.open-ocean-runtime-spec.v1",
        "instance_id": "i", "runtime_id": "r",
        "command": [sys.executable, "-c", "import time; time.sleep(120)"],
        "cwd": str(tmp_path), "env": {},
        "state_path": str(tmp_path / "state.json"), "log_path": str(tmp_path / "log.txt"),
        "runtime_url": "http://127.0.0.1:1", "health_url": "http://127.0.0.1:1/health",
    }), encoding="utf-8")
    seen: list[int] = []

    def refuse(_job, child):
        seen.append(child.pid)
        raise windows_job.WindowsJobError("simulated")

    with patch.dict(os.environ, {"OCEAN_RUNTIME_TOKEN": "t"}), \
            patch.object(windows_job, "assign_and_resume", refuse):
        with pytest.raises(runtime_supervisor.ProcessFenceError):
            runtime_supervisor.supervise(spec)
    assert seen, "the assignment was never attempted"
    assert _wait_for_exit(seen[0], 10000), "the unstarted child was left running"


@windows_only
def test_an_interrupt_during_job_setup_kills_the_unstarted_child_and_propagates(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema": "ellmos.open-ocean-runtime-spec.v1",
        "instance_id": "i", "runtime_id": "r",
        "command": [sys.executable, "-c", "import time; time.sleep(120)"],
        "cwd": str(tmp_path), "env": {},
        "state_path": str(tmp_path / "state.json"), "log_path": str(tmp_path / "log.txt"),
        "runtime_url": "http://127.0.0.1:1", "health_url": "http://127.0.0.1:1/health",
    }), encoding="utf-8")
    spawned: list[int] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        spawned.append(child.pid)
        return child

    def interrupted():
        raise KeyboardInterrupt

    with patch.dict(os.environ, {"OCEAN_RUNTIME_TOKEN": "t"}),             patch.object(runtime_supervisor.subprocess, "Popen", recording_popen),             patch.object(windows_job, "create_kill_on_close_job", interrupted):
        with pytest.raises(KeyboardInterrupt):  # not rewritten into a ProcessFenceError
            runtime_supervisor.supervise(spec)
    assert spawned, "no child was spawned"
    assert _wait_for_exit(spawned[0], 10000), "the suspended child was left behind"


def _write_spec(tmp_path, command):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema": "ellmos.open-ocean-runtime-spec.v1",
        "instance_id": "i", "runtime_id": "r", "command": command,
        "cwd": str(tmp_path), "env": {},
        "state_path": str(tmp_path / "state.json"), "log_path": str(tmp_path / "log.txt"),
        "runtime_url": "http://127.0.0.1:1", "health_url": "http://127.0.0.1:1/health",
    }), encoding="utf-8")
    return spec


@windows_only
def test_a_failing_kill_during_setup_cleanup_does_not_replace_the_primary_error(tmp_path):
    spec = _write_spec(tmp_path, [sys.executable, "-c", "import time; time.sleep(120)"])
    spawned: list[subprocess.Popen] = []
    waits: list[float | None] = []
    real_popen, real_wait = subprocess.Popen, subprocess.Popen.wait

    def recording_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        spawned.append(child)
        return child

    def spying_wait(self, timeout=None):
        waits.append(timeout)
        return real_wait(self, timeout=timeout)

    def interrupted():
        raise KeyboardInterrupt

    try:
        with patch.dict(os.environ, {"OCEAN_RUNTIME_TOKEN": "t"}),                 patch.object(runtime_supervisor, "REAP_WAIT_SECONDS", 0.2),                 patch.object(runtime_supervisor.subprocess, "Popen", recording_popen),                 patch.object(real_popen, "kill", side_effect=OSError("kill denied")),                 patch.object(real_popen, "wait", spying_wait),                 patch.object(windows_job, "create_kill_on_close_job", interrupted):
            with pytest.raises(KeyboardInterrupt) as caught:
                runtime_supervisor.supervise(spec)
    finally:
        for child in spawned:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=60)
    assert waits, "wait() was skipped after kill() failed"
    if hasattr(caught.value, "add_note"):
        assert "kill denied" in " ".join(getattr(caught.value, "__notes__", [])), (
            "the cleanup failure was not attached to the primary error"
        )


@windows_only
def test_a_failed_job_handle_close_is_reported_when_nothing_else_failed(tmp_path):
    spec = _write_spec(tmp_path, [sys.executable, "-c", "pass"])

    def refuse_close(_job):
        raise windows_job.WindowsJobError("close denied")

    with patch.dict(os.environ, {"OCEAN_RUNTIME_TOKEN": "t"}),             patch.object(windows_job, "close_job", refuse_close):
        with pytest.raises(runtime_supervisor.ProcessFenceError, match="close denied"):
            runtime_supervisor.supervise(spec)
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["close_error"] == "close denied"


@windows_only
def test_a_failed_job_handle_close_does_not_hide_an_active_primary_error(tmp_path):
    spec = _write_spec(tmp_path, [sys.executable, "-c", "import time; time.sleep(120)"])

    def refuse_close(_job):
        raise windows_job.WindowsJobError("close denied")

    with patch.dict(os.environ, {"OCEAN_RUNTIME_TOKEN": "t"}),             patch.object(windows_job, "close_job", refuse_close),             patch.object(runtime_supervisor._LoopbackControlServer, "handle_request",
                         side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt) as caught:
            runtime_supervisor.supervise(spec)
    if hasattr(caught.value, "add_note"):
        assert "close denied" in " ".join(caught.value.__notes__)


@windows_only
def test_a_grandchild_of_the_runtime_child_dies_with_the_supervisor_stop(tmp_path):
    child_script = tmp_path / "child.py"
    pid_file = tmp_path / "grandchild.pid"
    child_script.write_text(textwrap.dedent(
        """
        import os, subprocess, sys, time
        grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        tmp = sys.argv[1] + ".tmp"
        with open(tmp, "w") as handle:
            handle.write(str(grandchild.pid))
        os.replace(tmp, sys.argv[1])  # atomic: the test never sees a half-written pid
        time.sleep(120)
        """
    ), encoding="utf-8")
    state_path = tmp_path / "state.json"
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema": "ellmos.open-ocean-runtime-spec.v1",
        "instance_id": "fixture-instance", "runtime_id": "fixture-runtime",
        "command": [sys.executable, str(child_script), str(pid_file)],
        "cwd": str(tmp_path), "env": {},
        "state_path": str(state_path), "log_path": str(tmp_path / "log.txt"),
        "runtime_url": "http://127.0.0.1:1", "health_url": "http://127.0.0.1:1/health",
    }), encoding="utf-8")
    env = os.environ.copy()
    env["OCEAN_RUNTIME_TOKEN"] = "fixture-token"
    supervisor = subprocess.Popen(
        [sys.executable, str(Path(runtime_supervisor.__file__).resolve()), "--spec", str(spec)],
        cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    grandchild_pid = 0
    try:
        # Bounded polling on purpose: the readiness signal is the atomically replaced state
        # file plus the pid file, and neither offers a waitable handle.
        deadline = time.monotonic() + 30
        state = None
        while time.monotonic() < deadline:
            assert supervisor.poll() is None, f"supervisor exited early: {supervisor.returncode}"
            if state_path.is_file() and pid_file.is_file():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("control", {}).get("port"):
                    break
            time.sleep(0.02)
        assert state is not None, "no state receipt within 30 s"
        grandchild_pid = int(pid_file.read_text(encoding="ascii"))
        assert windows_job.process_is_alive(grandchild_pid)
        control = state["control"]
        request = urllib.request.Request(
            f"http://{control['host']}:{control['port']}/stop", method="POST",
            headers={"Authorization": f"Bearer {control['token']}"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            assert json.loads(response.read().decode("utf-8"))["status"] == "stopped"
        supervisor.wait(timeout=15)
        assert _wait_for_exit(grandchild_pid, 15000), "the grandchild survived the supervisor stop"
    finally:
        for pid in (grandchild_pid, supervisor.pid):
            if pid:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=60)
