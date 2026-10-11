"""Kill-on-close Windows job object for the supervised runtime child.

On Windows ``Popen.terminate()`` only ends the direct child, so helpers the runtime
starts (PowerShell, icacls, ...) would outlive a stop.  The supervisor starts the child
suspended, assigns it to a job created with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, and only
then resumes it, so no descendant can exist before the job holds the child.  Standard
library only (ctypes); every failure raises ``WindowsJobError`` -- callers must not fall
back to a direct-child-only stop.
"""

from __future__ import annotations

import ctypes
import os
from typing import Any

if os.name == "nt":
    from ctypes import wintypes

CREATE_SUSPENDED = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


class WindowsJobError(OSError):
    """A job object could not be created, filled, resumed or terminated."""


if os.name == "nt":  # pragma: no cover - exercised only on Windows
    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _kernel32() -> Any:
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.OpenProcess.restype = wintypes.HANDLE
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        return api


def _fail(what: str) -> WindowsJobError:
    return WindowsJobError(f"{what} (Win32-Fehler {ctypes.get_last_error()})")


def create_kill_on_close_job() -> int:
    """New job whose handle closing (also by supervisor death) kills its processes."""
    api = _kernel32()
    job = api.CreateJobObjectW(None, None)
    if not job:
        raise _fail("Job-Objekt konnte nicht angelegt werden")
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not api.SetInformationJobObject(
        job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(limits), ctypes.sizeof(limits),
    ):
        error = _fail("Kill-on-close-Limit konnte nicht gesetzt werden")
        api.CloseHandle(job)
        raise error
    return int(job)


def assign_and_resume(job: int, child: Any) -> None:
    """Put the suspended ``child`` (a Popen) into ``job``, then let it run."""
    api = _kernel32()
    handle = int(child._handle)  # type: ignore[attr-defined]
    if not api.AssignProcessToJobObject(job, handle):
        raise _fail("Runtime-Kind konnte dem Job-Objekt nicht zugewiesen werden")
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.restype = ctypes.c_long
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    status = ntdll.NtResumeProcess(handle)
    if status != 0:
        raise WindowsJobError(f"Runtime-Kind konnte nicht fortgesetzt werden (NTSTATUS {status:#x})")


def terminate_job(job: int, exit_code: int = 1) -> None:
    """End every process in the job, including descendants."""
    if not _kernel32().TerminateJobObject(job, exit_code):
        raise _fail("Job-Objekt konnte nicht beendet werden")


def close_job(job: int) -> None:
    _kernel32().CloseHandle(job)


def process_is_alive(pid: int) -> bool:
    """Fail-closed liveness: only a successful query that says "exited" returns False.

    A pid that no longer exists is dead (OpenProcess fails with ERROR_INVALID_PARAMETER);
    any other failure is reported as an error, never as "dead".
    """
    api = _kernel32()
    handle = api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: no such process
            return False
        raise _fail(f"Prozess {pid} konnte nicht abgefragt werden")
    try:
        code = wintypes.DWORD()
        if not api.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise _fail(f"Exitcode von Prozess {pid} nicht lesbar")
        return code.value == STILL_ACTIVE
    finally:
        api.CloseHandle(handle)
