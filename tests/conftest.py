"""Suite-wide process hygiene for tests that start a real OCEAN runtime.

Several tests drive `ocean.py` as a subprocess, and `ocean.py up`/`start` spawns a
supervisor which in turn spawns the runtime child. Nothing tied those grandchildren to
the test run: after a failed or interrupted test the supervisor kept running with a dead
parent, held its own loopback listener and even blocked `git worktree remove` on the tree
it was started from (T-20260912-577456824). The house rule is that whoever starts child
processes ends them with their own session -- there is deliberately no central orphan
reaper.

Two layers, on purpose:

1. **Windows job object** -- the real fix. pytest assigns *itself* to a job with
   ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``; every descendant inherits it, because
   `ocean_lifecycle` spawns the supervisor without ``CREATE_BREAKAWAY_FROM_JOB``. The
   kernel closes the handle when pytest exits *however* it exits, so this also covers the
   hard aborts that produced the orphan in the first place. A plain teardown cannot.
2. **Cross-platform sweep** -- a safety net that terminates leftover supervisors at the end
   of the session, and the same function the regression test uses to assert none remain.

Both layers identify "ours" by the **basetemp path in the command line**, never by process
name. A name-based match would also hit the production OCEAN service, which runs
`runtime_supervisor.py` from ``C:/_Local_DEV/runtimes/...`` and must never be touched by a
test run. `test_process_hygiene.py` asserts exactly that.
"""

from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

SUPERVISOR_MARKER = "runtime_supervisor.py"
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

if os.name == "nt":  # pragma: no cover - exercised only on Windows
    from ctypes import wintypes

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def kernel32() -> ctypes.WinDLL:
        return ctypes.WinDLL("kernel32", use_last_error=True)

    def create_kill_on_close_job() -> int | None:
        """A job object whose closure terminates everything assigned to it."""
        api = kernel32()
        job = api.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(
            job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            api.CloseHandle(job)
            return None
        return job


def _iter_processes() -> list[tuple[int, int, str]]:
    """Return (pid, ppid, command line) for every visible process.

    Standard library only: this repository ships no runtime dependencies, so psutil is
    not available to its tests either.
    """
    if os.name == "nt":
        completed = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-CimInstance Win32_Process | "
                "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return []
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, dict):
            payload = [payload]
        return [
            (int(entry.get("ProcessId") or 0), int(entry.get("ParentProcessId") or 0),
             entry.get("CommandLine") or "")
            for entry in payload
        ]

    completed = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,args="],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if completed.returncode != 0:
        return []
    rows = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return any(row[0] == pid for row in _iter_processes())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def find_test_supervisors(basetemp: Path) -> list[tuple[int, int, str]]:
    """Supervisor processes this test run is responsible for.

    Scoped by ``basetemp``, not by process name: the production runtime also runs
    ``runtime_supervisor.py`` and must never appear in this list.
    """
    needle = str(basetemp).replace("\\", "/").lower()
    return [
        (pid, ppid, command)
        for pid, ppid, command in _iter_processes()
        if SUPERVISOR_MARKER in command and needle in command.replace("\\", "/").lower()
    ]


def terminate_process_tree(pid: int) -> None:
    """Kill one process and its descendants, best effort."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True, timeout=60,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def _assign_self_to_kill_on_close_job() -> bool:
    """Put the pytest process into a kill-on-close job. False if unavailable."""
    if os.name != "nt":
        return False
    job = create_kill_on_close_job()
    if job is None:
        return False
    api = kernel32()
    if not api.AssignProcessToJobObject(job, api.GetCurrentProcess()):
        api.CloseHandle(job)
        return False
    # Deliberately kept open for the whole session: the kernel closing this handle on
    # process exit is what kills the tree, including after a hard abort.
    globals()["_OCEAN_TEST_JOB_HANDLE"] = job
    return True


@pytest.fixture(scope="session", autouse=True)
def _ocean_runtime_process_hygiene(tmp_path_factory):
    """Make every runtime process started by this suite die with the suite."""
    job_active = _assign_self_to_kill_on_close_job()
    basetemp = Path(tmp_path_factory.getbasetemp())

    yield {"job_active": job_active, "basetemp": basetemp}

    for pid, _ppid, _command in find_test_supervisors(basetemp):
        terminate_process_tree(pid)

    leftover = find_test_supervisors(basetemp)
    if leftover:  # pragma: no cover - only if neither layer worked
        print(
            f"\n[process-hygiene] {len(leftover)} runtime supervisor(s) survived teardown: "
            + ", ".join(str(pid) for pid, _, _ in leftover),
            file=sys.stderr,
        )
