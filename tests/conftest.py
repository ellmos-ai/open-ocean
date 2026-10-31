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
import time
from pathlib import Path

import pytest

# Make the repo root importable no matter what the caller's cwd is: invoking
# pytest from a foreign project root would otherwise leave the in-repo
# helpers (tools/, src/) unimportable during collection (T-20260920-823767362).
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class ProcessListError(RuntimeError):
    """The process table could not be read. Never to be treated as "no process"."""


def _windows_entry(entry: object) -> tuple[int, int, str]:
    """One Get-CimInstance record, or ProcessListError: a record without ids is not "a process"."""
    if not isinstance(entry, dict):
        raise ProcessListError(f"process listing entry is not an object: {entry!r}")
    pid, ppid, command = (entry.get(key) for key in ("ProcessId", "ParentProcessId", "CommandLine"))
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (pid, ppid)) or not (
        command is None or isinstance(command, str)
    ):
        raise ProcessListError(f"process listing entry has missing or mistyped fields: {entry!r}")
    return pid, ppid, command or ""


class ProcessListParseError(ProcessListError):
    """The listing ran but its output was not valid JSON: the one error worth re-reading."""


def _read_process_table(timeout: float = 120) -> list[tuple[int, int, str]]:
    """Return (pid, ppid, command line) for every visible process.

    Standard library only: this repository ships no runtime dependencies, so psutil is
    not available to its tests either.
    """
    # A failed read must not look like an empty process table: callers use "not in the list"
    # as proof of death, so an error is raised instead of returned as [] (fail-closed).
    try:
        if os.name == "nt":
            completed = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                    "Get-CimInstance Win32_Process | "
                    "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress",
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
        else:
            completed = subprocess.run(
                ["ps", "-eo", "pid=,ppid=,args="],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcessListError(f"process listing failed: {exc}") from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ProcessListError(
            f"process listing returned exit {completed.returncode} / empty output"
        )

    if os.name == "nt":
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ProcessListParseError(f"process listing is not valid JSON: {exc}") from exc
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not payload:
            raise ProcessListError("process listing has no entries")
        return [_windows_entry(entry) for entry in payload]

    rows = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    if not rows:
        raise ProcessListError("process listing has no parsable rows")
    return rows


LISTING_TIMEOUT = 120
LISTING_DEADLINE = 180  # seconds for all attempts together


def _iter_processes() -> list[tuple[int, int, str]]:
    """The process table, or ProcessListError. Re-reads a transient unparsable snapshot.

    The Windows listing is occasionally not valid JSON (seen once in ~60 runs of the
    hygiene tests: a process appearing or exiting while PowerShell serialises ~200 KB).
    Only that is retried, and only within LISTING_DEADLINE; a timeout, a failed command or
    a structurally wrong record is raised at once, and an empty or invalid result after the
    last attempt is still an error, never "no processes".
    """
    deadline = time.monotonic() + LISTING_DEADLINE
    for attempt in range(3):
        try:
            return _read_process_table(max(1.0, min(LISTING_TIMEOUT, deadline - time.monotonic())))
        except ProcessListParseError:
            if attempt == 2 or time.monotonic() >= deadline:
                raise
    raise AssertionError("unreachable")


SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87  # OpenProcess answer for a pid that does not exist


def handle_is_alive(api, handle) -> bool:
    """Is the process behind this SYNCHRONIZE handle still running?

    Waits on the process object instead of reading its exit code: STILL_ACTIVE (259) is a
    legal exit code, so a finished process can report it and look alive forever.
    """
    result = api.WaitForSingleObject(handle, 0)
    if result == WAIT_TIMEOUT:
        return True
    if result == WAIT_OBJECT_0:
        return False
    raise ProcessListError(f"WaitForSingleObject returned {result:#x}")


def open_process_for_wait(pid: int):  # pragma: no cover - exercised only on Windows
    """A handle that pins this process (a pid can be reused, a handle cannot), or None.

    None means the pid does not exist. Access denied is not "dead" and raises PermissionError.
    """
    api = kernel32()
    api.OpenProcess.restype = wintypes.HANDLE
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(SYNCHRONIZE, False, pid)
    if handle:
        return handle
    error = ctypes.get_last_error()
    if error == ERROR_INVALID_PARAMETER:
        return None
    if error == ERROR_ACCESS_DENIED:
        raise PermissionError(pid)
    raise ProcessListError(f"OpenProcess({pid}) failed with Windows error {error}")


def _windows_pid_is_alive(pid: int) -> bool:  # pragma: no cover - exercised only on Windows
    """Ask the kernel about this one pid instead of diffing a process listing.

    An error other than "no such process" raises: it must not read as "dead".
    """
    try:
        handle = open_process_for_wait(pid)
    except PermissionError:
        return True  # exists, merely not ours to open
    if handle is None:
        return False
    api = kernel32()
    try:
        return handle_is_alive(api, handle)
    finally:
        api.CloseHandle(handle)


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_is_alive(pid)
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
        group = os.getpgid(pid)
    except (ProcessLookupError, PermissionError, OSError):
        group = None
    # Never signal our own group: killpg on a process that shares the test runner's
    # group takes the runner down with it (exit 143). A supervisor spawned before
    # T-20260913-243123928 did exactly that.
    if group is not None and group != os.getpgrp():
        try:
            os.killpg(group, signal.SIGTERM)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
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


def pytest_addoption(parser):
    group = parser.getgroup("shard", "Deterministic sha256 test sharding (#3494)")
    group.addoption(
        "--shard-index",
        action="store",
        type=int,
        default=None,
        help="Zero-based shard index in [0, shard-count).",
    )
    group.addoption(
        "--shard-count",
        action="store",
        type=int,
        default=None,
        help="Total number of deterministic shards (K >= 1).",
    )


def pytest_collection_modifyitems(config, items):
    shard_index = config.getoption("--shard-index")
    shard_count = config.getoption("--shard-count")
    if shard_index is None and shard_count is None:
        return
    if shard_index is None or shard_count is None:
        raise pytest.UsageError("Both --shard-index and --shard-count must be specified together.")
    from tools.pytest_shard import filter_items_for_shard
    try:
        kept = filter_items_for_shard(items, shard_index, shard_count)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
    kept_set = set(kept)
    deselected = [item for item in items if item not in kept_set]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = kept
