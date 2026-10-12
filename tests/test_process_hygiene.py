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

import ast
import ctypes
import inspect
import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest

import conftest
from conftest import (
    ProcessListError,
    find_test_supervisors,
    process_is_alive,
    terminate_process_tree,
)

PRODUCTION_COMMAND = (
    '"C:\\Program Files\\Python312\\pythonw.exe" '
    "C:\\_Local_DEV\\runtimes\\open-ocean-ocean-full-laptop-hafenlicht-20260829\\tools\\"
    "runtime_supervisor.py --spec C:\\_Local_DEV\\ocean-full\\ocean.runtime-spec.json"
)


def _function_ast(func) -> ast.AST:
    """The function's own syntax tree -- comments and strings cannot fake a call here."""
    return ast.parse(textwrap.dedent(inspect.getsource(func)))


def _call_keywords(func, callee_suffix: str) -> set[str]:
    """Keyword argument names of the first call whose target ends in `callee_suffix`."""
    for node in ast.walk(_function_ast(func)):
        if isinstance(node, ast.Call):
            target = node.func
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name.endswith(callee_suffix):
                return {kw.arg for kw in node.keywords if kw.arg}
    return set()


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
def test_the_supervisor_is_spawned_into_its_own_session_on_posix():
    """Pins the production decision, not just the principle.

    `ocean_lifecycle` is the only place that spawns the supervisor. If it ever drops
    `start_new_session` again, the supervisor lands back in the caller's process group
    and the sweep's killpg becomes a self-signal.

    Read through the AST rather than the raw source: a substring check also matches the
    call inside a comment, so commenting the line out would leave the test green.
    """
    import tools.ocean_lifecycle as lifecycle

    spawn = _call_keywords(lifecycle._start_runtime_locked, "Popen")
    assert "start_new_session" in spawn, (
        "the supervisor spawn no longer passes start_new_session"
    )


def test_the_runtime_child_is_spawned_into_its_own_session_on_posix():
    """The supervisor must have a separate fence for its runtime child group."""
    import tools.runtime_supervisor as runtime_supervisor

    spawn = _call_keywords(runtime_supervisor.supervise, "Popen")
    assert "start_new_session" in spawn, (
        "the runtime child spawn no longer passes start_new_session"
    )


def test_a_failed_start_does_not_walk_away_from_its_supervisor():
    """The orphan the macOS CI actually tripped over.

    `--health-timeout 0.01` returns long before the supervisor writes its state file,
    so the graceful stop path cannot apply -- and the start used to just raise, leaving
    a live supervisor behind (CI showed it with ppid=1). The failing start has to end
    what it started, on every exit that is not success.
    """
    import tools.ocean_lifecycle as lifecycle

    tree = _function_ast(lifecycle._start_runtime_locked)
    cleanup_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_terminate_supervisor"
    ]
    assert cleanup_calls, "the start path never ends the supervisor it spawned"

    # In a `finally`, so an unexpected error inside the wait loop leaks nothing either.
    in_finally = any(
        call in ast.walk(handler)
        for node in ast.walk(tree) if isinstance(node, ast.Try)
        for handler in node.finalbody
        for call in cleanup_calls
    )
    assert in_finally, "the cleanup is not on a finally path; an early error would leak"


PID_REPORT_TIMEOUT = 30


def _read_line_within(stream, timeout: float) -> str:
    """readline() with a deadline: a parent that hangs must fail the test, not stall it.

    The reader thread is a daemon; the caller's `finally` kills the parent, which ends it.
    """
    box: list[str] = []
    reader = threading.Thread(target=lambda: box.append(stream.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    assert box, f"no line within {timeout}s -- the spawned parent is hanging"
    return box[0]


@pytest.mark.skipif(os.name != "nt", reason="job objects are a Windows mechanism")
def test_job_object_kills_a_grandchild_when_it_closes():
    """The mechanism the suite relies on, proven on real processes.

    Uses its own job so the suite's job is untouched, and a grandchild rather than a
    direct child, because the leaked supervisor was a grandchild of pytest.
    """
    api = conftest.kernel32()
    job = conftest.create_kill_on_close_job()
    assert job, "could not create a kill-on-close job object"

    # The parent must not create the grandchild before it is in the job: a descendant
    # born in that window is not covered and survives the close (flaky before, R19). So
    # the parent blocks on stdin until the test has assigned it, then spawns -- the order
    # is guaranteed by the pipe, not by a sleep.
    spawn = (
        "import subprocess,sys,time;"
        "sys.stdin.readline();"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        "print(p.pid,flush=True);"
        "time.sleep(120)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", spawn],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    handle = grandchild = None
    try:
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE -- what AssignProcessToJobObject needs
        handle = api.OpenProcess(0x0100 | 0x0001, False, parent.pid)
        assert handle, "could not open the spawned parent"
        assert api.AssignProcessToJobObject(job, handle), "could not assign to the job"
        parent.stdin.write("go\n")
        parent.stdin.flush()

        grandchild_pid = int(_read_line_within(parent.stdout, PID_REPORT_TIMEOUT).strip())
        # Pin the grandchild itself: the pid may be reused once it is gone, a handle may not.
        grandchild = conftest.open_process_for_wait(grandchild_pid)
        assert grandchild, "could not open the grandchild"
        assert conftest.handle_is_alive(api, grandchild), "grandchild did not start"

        api.CloseHandle(job)
        job = None

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and conftest.handle_is_alive(api, grandchild):
            time.sleep(0.5)
        assert not conftest.handle_is_alive(api, grandchild), (
            f"grandchild {grandchild_pid} survived the job closing"
        )
    finally:
        try:
            parent.stdin.close()
        except OSError:
            pass
        if handle:
            api.CloseHandle(ctypes.c_void_p(handle))
        if grandchild:
            api.CloseHandle(ctypes.c_void_p(grandchild))
        if job:
            api.CloseHandle(job)
        terminate_process_tree(parent.pid)


def _fake_run(returncode=0, stdout=""):
    class _Done:
        pass

    done = _Done()
    done.returncode, done.stdout = returncode, stdout
    return lambda *args, **kwargs: done


@pytest.mark.parametrize("returncode, stdout", [
    (1, ""),          # the listing command failed
    (0, ""),          # ... or produced nothing
    (0, "not json"),  # ... or garbage (Windows reader; on POSIX no row parses)
    (0, "[]"),        # a live system always has processes
])
def test_a_failed_process_listing_raises_instead_of_reporting_no_processes(
    monkeypatch, returncode, stdout,
):
    """A broken read used to come back as [] and read as "everything is dead"."""
    monkeypatch.setattr(conftest.subprocess, "run", _fake_run(returncode, stdout))
    with pytest.raises(ProcessListError):
        conftest._iter_processes()


def test_a_transient_bad_listing_is_read_again(monkeypatch):
    answers = iter([_fake_run(0, "not json")(), _fake_run(
        0, '[{"ProcessId": 7, "ParentProcessId": 1, "CommandLine": "x"}]',
    )()])
    monkeypatch.setattr(conftest.subprocess, "run", lambda *a, **k: next(answers))
    if os.name != "nt":
        pytest.skip("the JSON listing is the Windows reader")
    assert conftest._iter_processes() == [(7, 1, "x")]


def test_a_listing_that_cannot_be_run_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 1)

    monkeypatch.setattr(conftest.subprocess, "run", boom)
    with pytest.raises(ProcessListError):
        conftest._iter_processes()


def test_supervisor_sweep_does_not_swallow_a_failed_listing(monkeypatch, tmp_path):
    monkeypatch.setattr(conftest.subprocess, "run", _fake_run(1, ""))
    with pytest.raises(ProcessListError):
        find_test_supervisors(tmp_path)


def test_process_is_alive_tells_a_live_process_from_an_exited_one():
    assert process_is_alive(os.getpid())
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    child_pid = child.pid
    del child  # release the handle so Windows no longer keeps the pid object around
    assert not process_is_alive(child_pid)


class _FakeKernel:
    """Answers WaitForSingleObject like the kernel; GetExitCodeProcess lies like a 259 exit."""

    def __init__(self, wait_result):
        self.wait_result = wait_result

    def WaitForSingleObject(self, handle, milliseconds):
        return self.wait_result

    def GetExitCodeProcess(self, handle, code):
        raise AssertionError("liveness must not be decided by the exit code")


def test_a_process_that_exited_with_code_259_is_not_alive():
    """STILL_ACTIVE is a legal exit code; the signalled process object says it ended."""
    assert not conftest.handle_is_alive(_FakeKernel(conftest.WAIT_OBJECT_0), 1)


def test_an_unsignalled_process_is_alive():
    assert conftest.handle_is_alive(_FakeKernel(conftest.WAIT_TIMEOUT), 1)


def test_an_unexpected_wait_result_raises():
    with pytest.raises(ProcessListError):
        conftest.handle_is_alive(_FakeKernel(0xFFFFFFFF), 1)  # WAIT_FAILED


@pytest.mark.skipif(os.name != "nt", reason="the JSON listing is the Windows reader")
@pytest.mark.parametrize("payload", [
    "[{}]",
    '[{"ProcessId": 7}]',
    '[{"ProcessId": "7", "ParentProcessId": 1, "CommandLine": "x"}]',
    '[{"ProcessId": 7, "ParentProcessId": 1, "CommandLine": 5}]',
    "[1]",
])
def test_a_structurally_wrong_record_raises(monkeypatch, payload):
    monkeypatch.setattr(conftest.subprocess, "run", _fake_run(0, payload))
    with pytest.raises(ProcessListError):
        conftest._iter_processes()


@pytest.mark.skipif(os.name != "nt", reason="the JSON listing is the Windows reader")
def test_an_idle_process_record_with_no_command_line_is_accepted(monkeypatch):
    monkeypatch.setattr(conftest.subprocess, "run", _fake_run(
        0, '[{"ProcessId": 0, "ParentProcessId": 0, "CommandLine": null}]',
    ))
    assert conftest._iter_processes() == [(0, 0, "")]


def test_a_timeout_is_not_retried(monkeypatch):
    calls = []

    def boom(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("ps", 1)

    monkeypatch.setattr(conftest.subprocess, "run", boom)
    with pytest.raises(ProcessListError):
        conftest._iter_processes()
    assert len(calls) == 1


@pytest.mark.skipif(os.name != "nt", reason="the JSON listing is the Windows reader")
def test_retries_stop_at_the_total_deadline(monkeypatch):
    calls = []
    monkeypatch.setattr(conftest, "LISTING_DEADLINE", -1)
    monkeypatch.setattr(conftest.subprocess, "run",
                        lambda *a, **k: calls.append(1) or _fake_run(0, "not json")())
    with pytest.raises(ProcessListError):
        conftest._iter_processes()
    assert len(calls) == 1
