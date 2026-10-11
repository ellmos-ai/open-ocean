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


def test_the_windows_start_puts_the_child_into_a_job_before_it_runs():
    """Pins the production decision on every platform (read through the AST)."""
    assert _calls(runtime_supervisor.supervise, "create_kill_on_close_job"), (
        "supervise no longer creates a kill-on-close job"
    )
    assert _calls(runtime_supervisor.supervise, "assign_and_resume"), (
        "supervise no longer assigns the child to the job"
    )
    source = inspect.getsource(runtime_supervisor.supervise)
    assert "CREATE_SUSPENDED" in source, "the child is no longer started suspended"
    assert _calls(windows_job.assign_and_resume, "AssignProcessToJobObject"), (
        "the job assignment disappeared from assign_and_resume"
    )
    order = [
        node.func.attr for node in _calls(windows_job.assign_and_resume, "AssignProcessToJobObject")
    ] + [node.func.attr for node in _calls(windows_job.assign_and_resume, "NtResumeProcess")]
    assert order == ["AssignProcessToJobObject", "NtResumeProcess"], "resume must follow assignment"


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
