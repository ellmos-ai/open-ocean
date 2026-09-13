"""Regression cover for T-20260912-577456824.

A test run used to leave `tools/runtime_supervisor.py` running with a dead parent. It
held its own loopback listener and blocked `git worktree remove` on the tree it was
started from. Three things have to hold:

1. no supervisor of *this* run survives into the run itself,
2. the production runtime is never a candidate for termination, and
3. the Windows job object really does kill a grandchild when it closes.

Point 2 matters most. The obvious implementation -- match on the process name -- would
also select the live OCEAN service, which runs `runtime_supervisor.py` as well. The scope
is therefore the basetemp path, asserted here against a synthetic process table so the
check never needs a running production service to prove it.
"""

from __future__ import annotations

import ctypes
import inspect
import os
import subprocess
import sys
import time

import pytest

import conftest
from conftest import find_test_supervisors, process_is_alive, terminate_process_tree

PRODUCTION_COMMAND = (
    '"C:\\Program Files\\Python312\\pythonw.exe" '
    "C:\\_Local_DEV\\runtimes\\open-ocean-ocean-full-laptop-hafenlicht-20260829\\tools\\"
    "runtime_supervisor.py --spec C:\\_Local_DEV\\ocean-full\\ocean.runtime-spec.json"
)


def test_no_supervisor_of_this_run_is_left_behind(tmp_path_factory):
    """The orphan this ticket is about would show up here."""
    leftover = find_test_supervisors(tmp_path_factory.getbasetemp())
    assert leftover == [], (
        "runtime supervisor(s) from this test run are still alive: "
        + "; ".join(f"pid={pid} ppid={ppid}" for pid, ppid, _ in leftover)
    )


def test_production_runtime_is_never_selected(tmp_path, monkeypatch):
    """Name matching would kill the live service; path scoping must not."""
    ours = (
        f'"{sys.executable}" {tmp_path}/tools/runtime_supervisor.py '
        f"--spec {tmp_path}/ocean.runtime-spec.json"
    )
    monkeypatch.setattr(conftest, "_iter_processes", lambda: [
        (4242, 1, ours),
        (5184, 5780, PRODUCTION_COMMAND),
        (9001, 1, f'"{sys.executable}" -m pytest'),
    ])

    selected = find_test_supervisors(tmp_path)

    assert [pid for pid, _, _ in selected] == [4242]
    assert all("runtimes" not in command for _, _, command in selected), (
        "the production runtime was selected for termination"
    )


def test_scope_is_the_basetemp_not_the_process_name(tmp_path, monkeypatch):
    """A supervisor from a different test root is not ours to kill either."""
    other_root = tmp_path.parent / "some-other-run"
    monkeypatch.setattr(conftest, "_iter_processes", lambda: [
        (4243, 1, f'"{sys.executable}" {other_root}/tools/runtime_supervisor.py --spec x'),
    ])

    assert find_test_supervisors(tmp_path) == []


@pytest.mark.skipif(os.name == "nt", reason="process groups are a POSIX mechanism")
def test_the_sweep_never_signals_its_own_process_group(monkeypatch):
    """The macOS CI failure this covers was the suite killing itself.

    `ocean_lifecycle` used to spawn the supervisor without `start_new_session`, so it
    stayed in pytest's process group. When the end-of-session sweep then called
    `terminate_process_tree`, `os.killpg` delivered SIGTERM to that shared group -- and
    the job ended with exit 143 (T-20260913-243123928). Measured on a Mac: a child
    spawned the old way reports `os.getpgid(child) == os.getpgrp()`.
    """
    killed_groups = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed_groups.append(pgid))
    signalled = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signalled.append(pid))
    # A pid that shares our group -- exactly the old supervisor's situation.
    monkeypatch.setattr(os, "getpgid", lambda pid: os.getpgrp())

    terminate_process_tree(4242)

    assert killed_groups == [], "the sweep signalled its own process group"
    assert signalled == [4242], "the single process was not terminated either"


@pytest.mark.skipif(os.name == "nt", reason="process groups are a POSIX mechanism")
def test_the_supervisor_is_spawned_into_its_own_session_on_posix(monkeypatch):
    """Pins the production decision, not just the principle.

    `ocean_lifecycle` is the only place that spawns the supervisor. If it ever drops
    `start_new_session` again, the supervisor lands back in the caller's process group
    and the sweep's killpg becomes a self-signal.
    """
    import tools.ocean_lifecycle as lifecycle

    captured = {}

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.pid = -1

    monkeypatch.setattr(lifecycle.subprocess, "Popen", _FakePopen)

    source = inspect.getsource(lifecycle._start_runtime_locked)
    assert "start_new_session=start_new_session" in source, (
        "the supervisor spawn no longer passes start_new_session"
    )
    assert 'start_new_session = os.name != "nt"' in source, (
        "start_new_session is no longer enabled on POSIX"
    )


@pytest.mark.skipif(os.name != "nt", reason="job objects are a Windows mechanism")
def test_job_object_kills_a_grandchild_when_it_closes():
    """The mechanism the suite relies on, proven on real processes.

    Uses its own job so the suite's job is untouched, and a grandchild rather than a
    direct child, because the leaked supervisor was a grandchild of pytest.
    """
    api = conftest.kernel32()
    job = conftest.create_kill_on_close_job()
    assert job, "could not create a kill-on-close job object"

    spawn = (
        "import subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        "print(p.pid,flush=True);"
        "time.sleep(120)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", spawn],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    handle = None
    try:
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE -- what AssignProcessToJobObject needs
        handle = api.OpenProcess(0x0100 | 0x0001, False, parent.pid)
        assert handle, "could not open the spawned parent"
        assert api.AssignProcessToJobObject(job, handle), "could not assign to the job"

        grandchild_pid = int(parent.stdout.readline().strip())
        assert process_is_alive(grandchild_pid), "grandchild did not start"

        api.CloseHandle(job)
        job = None

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and process_is_alive(grandchild_pid):
            time.sleep(0.5)
        assert not process_is_alive(grandchild_pid), (
            f"grandchild {grandchild_pid} survived the job closing"
        )
    finally:
        if handle:
            api.CloseHandle(ctypes.c_void_p(handle))
        if job:
            api.CloseHandle(job)
        terminate_process_tree(parent.pid)
