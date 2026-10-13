"""Bounded wheel transactions for an existing, operator-selected Python environment.

This is an operation of Ocean's transaction engine. It neither creates an
environment nor resolves a target from request paths. Authorization remains
with the calling Installer; planning and verification never install packages.
"""

from __future__ import annotations

import base64
import configparser
import contextlib
import csv
import hashlib
import io
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from copy import deepcopy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

PLAN_SCHEMA = "ellmos.ocean.python-packages.plan.v1"
PROFILE_SCHEMA = "ellmos.ocean.python-environment-profile.v1"
RECEIPT_SCHEMA = "ellmos.ocean.python-packages.receipt.v1"
CHECKS = {"profile-binding", "environment-binding", "wheel-closure", "beforestate", "no-apply"}
_LEAF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^module:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_FILES = 100000
_MAX_WHEEL_BYTES = 256 * 1024 * 1024
_MAX_EXPANDED_BYTES = 512 * 1024 * 1024
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_HELD = threading.local()


class PackageError(RuntimeError):
    """The package operation has no valid, current technical authority."""


def bounded_json(value: Any, *, limit: int = _MAX_EXPANDED_BYTES, canonical=False) -> bytes:
    # Check plain DTO complexity/individual strings before an encoder can
    # materialize one oversized escaped chunk. No caller-defined serializers.
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        _require(count <= _MAX_FILES * 20 and depth <= 64, "JSON DTO complexity exceeds bound")
        if type(item) is str:
            _require(len(item) * 6 <= limit, "JSON string exceeds byte bound")
        elif type(item) is dict:
            _require(len(item) <= _MAX_FILES * 20, "JSON object complexity exceeds bound")
            _require(all(type(key) is str for key in item), "plain JSON object keys required")
            stack.extend((element, depth + 1) for pair in item.items() for element in pair)
        elif type(item) is list or type(item) is tuple:
            _require(len(item) <= _MAX_FILES * 20, "JSON array complexity exceeds bound")
            stack.extend((element, depth + 1) for element in item)
        else:
            _require(type(item) in {int, float, bool, type(None)}, "plain JSON DTO values required")
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                              separators=(",", ":") if canonical else None, allow_nan=False)
    chunks = []
    total = 0
    for chunk in encoder.iterencode(value):
        raw = chunk.encode("utf-8")
        total += len(raw)
        _require(total <= limit, "encoded JSON exceeds byte bound")
        chunks.append(raw)
    return b"".join(chunks)


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(bounded_json(value, canonical=True)).hexdigest()


def _with_hash(value: dict) -> dict:
    return {**value, "content_hash": canonical_hash(value)}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise PackageError(message)


def _name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _read_bytes(path: Path, limit: int = _MAX_WHEEL_BYTES) -> bytes:
    """Bounded single capture, rejecting special files and changed identities."""
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as file:
        before = os.fstat(file.fileno())
        _require((before.st_mode & 0o170000) == 0o100000 and before.st_size <= limit,
                 "unsupported or oversized technical input")
        data = file.read(limit + 1)
        after = os.fstat(file.fileno())
    current = path.lstat()
    _require(len(data) <= limit and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
             == (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns),
             "technical input changed during capture")
    return data


def _json_bytes(path: Path, limit: int = _MAX_EXPANDED_BYTES) -> tuple[bytes, dict]:
    raw = _read_bytes(path, limit)
    value = json.loads(raw)
    _require(isinstance(value, dict), "JSON object required")
    return raw, value


def _mutex_path(profile: dict) -> Path:
    root = Path(profile["venv"])
    _require(root.resolve(strict=True) == Path(os.path.abspath(root)),
             "configured environment must be its canonical non-symlink identity")
    identity = os.path.normcase(str(root))
    return root.parent / (".ocean-python-" + hashlib.sha256(identity.encode()).hexdigest() + ".lock")


@contextlib.contextmanager
def _venv_mutex(profile: dict):
    """One kernel lock for this target across profiles, journals and processes.

    The coordination file is outside the environment and is never deleted: a
    deleted/recreated lock could give concurrent writers different inodes.
    """
    path = _mutex_path(profile)
    held = getattr(_HELD, "targets", set())
    prior_fds = getattr(_HELD, "fds", {})
    prior_job_name = getattr(_HELD, "job_name", None)
    if str(path) in held:
        yield
        return
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    acquired = False
    try:
        state = os.fstat(descriptor)
        _require((state.st_mode & 0o170000) == 0o100000 and not path.is_symlink()
                 and (state.st_dev, state.st_ino) == (path.stat().st_dev, path.stat().st_ino),
                 "target mutex identity is not a regular stable file")
        if state.st_size == 0:
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise PackageError("selected environment has another active package operation") from exc
        acquired = True
        if os.name == "nt":
            _guard_windows_writer(path)
        _HELD.targets = held | {str(path)}
        _HELD.fds = {**prior_fds, str(path): descriptor}
        _HELD.job_name = "Global\\ellmos-ocean-python-" + hashlib.sha256(str(path).encode()).hexdigest()
        yield
    finally:
        _HELD.targets = held
        _HELD.fds = prior_fds
        _HELD.job_name = prior_job_name
        if acquired:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            # POSIX closes this owner's reference only. An inherited writer FD
            # retains the same open-file-description lock after abrupt exit.
        os.close(descriptor)


@contextlib.contextmanager
def package_transaction(plan: dict):
    """The original outer transaction context, shared by thin native consumers."""
    _require(plan.get("content_hash") == canonical_hash(
        {key: value for key, value in plan.items() if key != "content_hash"}),
        "bound package plan required for outer transaction")
    request = plan["request"]
    _, profile = _profile(request["profile_id"], request["profile_sha256"])
    with _venv_mutex(profile):
        yield


def _serialized(function):
    import functools
    @functools.wraps(function)
    def operation(value, *args, **kwargs):
        request = value.get("request", value)
        _, profile = _profile(request["profile_id"], request["profile_sha256"])
        with _venv_mutex(profile):
            return function(value, *args, **kwargs)
    return operation


def _relative(path: Path, root: Path) -> str:
    # resolve() alone would hide symlinks before the ownership check.
    absolute = Path(os.path.abspath(path))
    _require(absolute.is_relative_to(root), "package path escapes the selected environment")
    for part in [absolute, *absolute.parents]:
        if part == root.parent:
            break
        _require(not part.is_symlink(), "package path contains a symlink")
    return absolute.relative_to(root).as_posix()


def _profile(profile_id: str, digest: str) -> tuple[bytes, dict]:
    _require(isinstance(profile_id, str) and bool(_LEAF.fullmatch(profile_id))
             and profile_id not in {".", ".."}, "safe configured profile identity required")
    _require(isinstance(digest, str) and bool(_SHA.fullmatch(digest)), "profile SHA-256 required")
    configured = os.environ.get("OCEAN_PYTHON_PROFILES_ROOT", "")
    _require(bool(configured), "operator-bound Python profile source is unavailable")
    root = Path(configured)
    _require(root.is_absolute() and root.is_dir() and not root.is_symlink(),
             "configured profiles root must be an existing absolute directory")
    path = root / (profile_id + ".json")
    _relative(path, root)
    _require(path.is_file(), "configured profile source is unavailable")
    raw, value = _json_bytes(path, 64 * 1024)
    _require(hashlib.sha256(raw).hexdigest() == digest, "configured profile bytes changed")
    _require(set(value) == {"schema", "id", "host", "interpreter", "venv", "artifact_root"}
             and value["schema"] == PROFILE_SCHEMA and value["id"] == profile_id,
             "unsupported configured environment profile")
    _require(value["host"].casefold() == platform.node().casefold(), "profile belongs to another host")
    venv = Path(value["venv"])
    artifacts = Path(value["artifact_root"])
    interpreter = Path(value["interpreter"])
    _require(venv.is_absolute() and venv.is_dir() and not venv.is_symlink(),
             "profile must select an existing environment")
    _require(artifacts.is_absolute() and artifacts.is_dir() and not artifacts.is_symlink(),
             "profile artifact directory is unavailable")
    _require(not artifacts.resolve(strict=True).is_relative_to(venv.resolve(strict=True)),
             "artifact snapshots must be outside the selected environment")
    _require(interpreter.is_absolute() and interpreter.is_file()
             and Path(os.path.abspath(interpreter)).is_relative_to(venv)
             and interpreter.parent.name in {"bin", "Scripts"},
             "interpreter is not the selected environment executable")
    return raw, value


class _WindowsJob:
    """No breakaway; all descendants must physically leave this job before return."""

    def __init__(self, name=None):
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("process_limit", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_longlong) for name in (
                "user", "kernel", "period_user", "period_kernel")] + [
                (name, wintypes.DWORD) for name in ("faults", "total", "active", "terminated")]
        class ThreadEntry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                        ("thread", wintypes.DWORD), ("owner", wintypes.DWORD),
                        ("priority", wintypes.LONG), ("delta", wintypes.LONG),
                        ("flags", wintypes.DWORD)]
        self.ctypes, self.Accounting, self.ThreadEntry = ctypes, Accounting, ThreadEntry
        self.primary_threads = {}
        self.process_handles = {}
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Thread32First": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
            "Thread32Next": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
            "OpenThread": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
            "IsProcessInJob": ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.api.CreateJobObjectW(None, name)
        _require(bool(self.handle), "cannot create package process job")
        if name is not None and self.active():
            self.api.CloseHandle(self.handle)
            self.handle = None
            raise PackageError("target still has a live managed package writer")
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.api.CloseHandle(self.handle)
            self.handle = None
            raise PackageError("cannot configure package process job")

    def bind(self, pid: int):
        # CreateProcessW returns this exact owned process handle with query
        # access. No PID-based reopen or unnecessary rights are requested.
        process = self.process_handles.get(pid)
        _require(bool(process), "actual created package process handle is missing")
        bound = self.ctypes.c_int()
        _require(bool(self.api.IsProcessInJob(process, self.handle, self.ctypes.byref(bound)))
                 and bound.value, "package launcher was not born in the target job")

    def resume(self, pid: int):
        _require(self.active() == 1, "unexpected pre-resume package job scope")
        thread = self.primary_threads.pop(pid, None)
        _require(bool(thread), "actual primary-thread handle is missing")
        try:
            _require(self.api.ResumeThread(thread) == 1,
                     "package primary-thread resume is unconfirmed")
        finally:
            _require(bool(self.api.CloseHandle(thread)), "primary-thread handle close failed")

    def launch(self, command: list[str], env: dict):
        return _WindowsProcess(self, command, env)

    def active(self) -> int:
        state = self.Accounting()
        _require(bool(self.api.QueryInformationJobObject(
            self.handle, 1, self.ctypes.byref(state), self.ctypes.sizeof(state), None)),
            "cannot confirm package job process count")
        return state.active

    def terminate(self):
        if self.active():
            _require(bool(self.api.TerminateJobObject(self.handle, 1)),
                     "cannot terminate entire package job")
        deadline = time.monotonic() + 20
        while self.active():
            _require(time.monotonic() < deadline, "package job termination is unconfirmed")
            time.sleep(0.01)

    def close(self):
        if self.handle:
            try:
                self.terminate()
            finally:
                for thread in self.primary_threads.values():
                    _require(bool(self.api.CloseHandle(thread)), "pending primary-thread close failed")
                self.primary_threads.clear()
                _require(bool(self.api.CloseHandle(self.handle)), "package job close failed")
                self.handle = None


class _WindowsProcess:
    """SDK JOB_LIST attaches the suspended launcher atomically at process birth.

    No Popen fallback: unsupported Windows/kernel attributes fail before code.
    HANDLE_LIST inherits only the three explicitly created pipe handles.
    """

    def __init__(self, job, command, env):
        import ctypes
        import msvcrt
        from ctypes import wintypes
        _require(sys.getwindowsversion().major >= 10, "atomic job launch requires Windows 10+")
        self.job, self.api, self.returncode = job, job.api, None
        self.handle = None
        self.stdin = self.stdout = self.stderr = None
        class Security(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", wintypes.BOOL)]
        class Startup(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("reserved", wintypes.LPWSTR),
                        ("desktop", wintypes.LPWSTR), ("title", wintypes.LPWSTR)] + [
                        (name, wintypes.DWORD) for name in ("x", "y", "width", "height", "xchars", "ychars", "fill", "flags")] + [
                        ("show", wintypes.WORD), ("reserved_size", wintypes.WORD),
                        ("reserved_bytes", ctypes.c_void_p), ("stdin", wintypes.HANDLE),
                        ("stdout", wintypes.HANDLE), ("stderr", wintypes.HANDLE)]
        class Extended(ctypes.Structure):
            _fields_ = [("startup", Startup), ("attributes", ctypes.c_void_p)]
        class ProcessInfo(ctypes.Structure):
            _fields_ = [("process", wintypes.HANDLE), ("thread", wintypes.HANDLE),
                        ("pid", wintypes.DWORD), ("tid", wintypes.DWORD)]
        declarations = {
            "CreatePipe": ([ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(Security), wintypes.DWORD], wintypes.BOOL),
            "SetHandleInformation": ([wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD], wintypes.BOOL),
            "InitializeProcThreadAttributeList": ([ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)], wintypes.BOOL),
            "UpdateProcThreadAttribute": ([ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL),
            "DeleteProcThreadAttributeList": ([ctypes.c_void_p], None),
            "CreateProcessW": ([wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(Extended), ctypes.POINTER(ProcessInfo)], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "GetExitCodeProcess": ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        handles, attributes = set(), None
        streams = []
        initialized = False
        info = ProcessInfo()
        try:
            security = Security(ctypes.sizeof(Security), None, True)
            pairs = []
            for _ in range(3):
                read, write = wintypes.HANDLE(), wintypes.HANDLE()
                _require(bool(self.api.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(security), 0)),
                         "cannot create package launch pipes")
                handles.update((read.value, write.value))
                pairs.append((read.value, write.value))
            parent_handles = [pairs[0][1], pairs[1][0], pairs[2][0]]
            child_handles = (wintypes.HANDLE * 3)(pairs[0][0], pairs[1][1], pairs[2][1])
            job_handles = (wintypes.HANDLE * 1)(job.handle)
            for handle in parent_handles:
                _require(bool(self.api.SetHandleInformation(handle, 1, 0)), "cannot exclude parent pipe inheritance")
            size = ctypes.c_size_t()
            result = self.api.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            _require(not result and ctypes.get_last_error() == 122 and 0 < size.value <= 1048576,
                     "atomic job attribute sizing unsupported")
            attributes = ctypes.create_string_buffer(size.value)
            _require(bool(self.api.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size))),
                     "cannot initialize atomic job attributes")
            initialized = True
            # Microsoft SDK: INPUT (0x20000) | HandleList (2) / JobList (13).
            for key, value in ((0x20002, child_handles), (0x2000D, job_handles)):
                _require(bool(self.api.UpdateProcThreadAttribute(attributes, 0, key, value,
                              ctypes.sizeof(value), None, None)), "atomic job/handle-list unsupported")
            startup = Extended()
            startup.startup.cb = ctypes.sizeof(Extended)
            startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = child_handles
            startup.attributes = ctypes.cast(attributes, ctypes.c_void_p)
            command_line = subprocess.list2cmdline(command)
            environment = "\0".join(key + "=" + value for key, value in sorted(env.items())) + "\0\0"
            _require(len(command_line) <= 32766 and len(environment) <= 1048576,
                     "native package launch DTO exceeds bound")
            flags = 0x00080000 | 0x00000400 | 0x00000004 | 0x08000000 | 0x00000200
            _require(bool(self.api.CreateProcessW(command[0], ctypes.create_unicode_buffer(command_line),
                     None, None, True, flags, ctypes.create_unicode_buffer(environment), None,
                     ctypes.byref(startup), ctypes.byref(info))), "atomic job process creation failed")
            self.handle, self.pid = info.process, info.pid
            job.primary_threads[self.pid] = info.thread
            job.process_handles[self.pid] = info.process
            job.bind(self.pid)  # physical membership, before any primary-thread resume.
            for handle in child_handles:
                _require(bool(self.api.CloseHandle(handle)), "child pipe close failed")
                handles.remove(handle)
            for handle, mode in zip(parent_handles, ("wb", "rb", "rb")):
                descriptor = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_WRONLY if mode == "wb" else os.O_RDONLY))
                handles.remove(handle)
                streams.append(os.fdopen(descriptor, mode, buffering=0))
            self.stdin, self.stdout, self.stderr = streams
        except BaseException:
            for stream in streams:
                stream.close()
            if info.process:
                job.terminate()
                _require(bool(self.api.CloseHandle(info.process)), "failed launch process close failed")
                thread = job.primary_threads.pop(info.pid, None)
                if thread:
                    _require(bool(self.api.CloseHandle(thread)), "failed launch primary-thread close failed")
                self.handle = None
                job.process_handles.pop(info.pid, None)
            raise
        finally:
            if initialized:
                self.api.DeleteProcThreadAttributeList(attributes)
            for handle in handles:
                _require(bool(self.api.CloseHandle(handle)), "untransferred launch handle close failed")

    def poll(self):
        result = self.api.WaitForSingleObject(self.handle, 0)
        _require(result in (0, 258), "package process wait is unconfirmed")
        if result == 0:
            from ctypes import wintypes
            status = wintypes.DWORD()
            _require(bool(self.api.GetExitCodeProcess(self.handle, self.job.ctypes.byref(status))),
                     "package process exit code is unconfirmed")
            self.returncode = status.value
        return self.returncode

    def wait(self, timeout=20):
        _require(self.api.WaitForSingleObject(self.handle, int(timeout * 1000)) == 0,
                 "package process termination is unconfirmed")
        return self.poll()

    def kill(self):
        _require(bool(self.api.TerminateProcess(self.handle, 1)), "package launcher termination failed")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            if self.poll() is None:
                self.job.terminate()
            self.wait()
        finally:
            for stream in (self.stdin, self.stdout, self.stderr):
                if stream is not None:
                    stream.close()
            _require(bool(self.api.CloseHandle(self.handle)), "package process handle close failed")
            self.job.process_handles.pop(self.pid, None)
            self.handle = None


def _guard_windows_writer(path: Path) -> None:
    # A named kernel job remains associated with its process tree. Recovery
    # never treats an inherited parent's released file lock as writer death.
    probe = _WindowsJob()
    try:
        from ctypes import wintypes
        probe.api.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        probe.api.OpenJobObjectW.restype = wintypes.HANDLE
        name = "Global\\ellmos-ocean-python-" + hashlib.sha256(str(path).encode()).hexdigest()
        handle = probe.api.OpenJobObjectW(0x0004, False, name)
        if not handle:
            _require(probe.ctypes.get_last_error() == 2, "cannot verify target writer job absence")
            return
        try:
            state = probe.Accounting()
            _require(bool(probe.api.QueryInformationJobObject(
                handle, 1, probe.ctypes.byref(state), probe.ctypes.sizeof(state), None))
                and state.active == 0, "target still has a live managed package writer")
        finally:
            probe.api.CloseHandle(handle)
    finally:
        probe.close()


def _run(command: list[str], *, timeout: float = 120) -> str:
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PIP_", "PYTHON"))}
    # The documented null config disables global/user/site pip configuration.
    env.update(PYTHONIOENCODING="utf-8", PIP_CONFIG_FILE=os.devnull,
               PIP_DISABLE_PIP_VERSION_CHECK="1")
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | 0x00000004} if os.name == "nt"
               else {"start_new_session": True})
    job = _WindowsJob(getattr(_HELD, "job_name", None)) if os.name == "nt" else None
    if os.name != "nt":
        fds = getattr(_HELD, "fds", {})
        for path, descriptor in fds.items():
            state, current = os.fstat(descriptor), Path(path).stat()
            _require((state.st_dev, state.st_ino) == (current.st_dev, current.st_ino),
                     "inherited target lock identity changed")
        if fds:
            _require(len(fds) == 1, "package writer must have one target lock context")
            options["pass_fds"] = tuple(fds.values())
            env["OCEAN_PACKAGE_LOCK_FD"] = str(next(iter(fds.values())))
    try:
        launch = command
        payload = None
        if job is not None:
            # This trusted no-site launcher blocks on stdin and cannot start the
            # actual command or descendants until the parent confirms job binding.
            wrapper = ("import json,subprocess,sys; data=sys.stdin.buffer.readline(1048577);"
                       "assert len(data)<=1048576 and data.endswith(b'\\n'); command=json.loads(data);"
                       "raise SystemExit(subprocess.run(command,stdin=subprocess.DEVNULL).returncode)")
            launch = [command[0], "-I", "-S", "-B", "-c", wrapper]
            payload = bounded_json(command, limit=1024 * 1024) + b"\n"
            if len(payload) > 1024 * 1024:
                job.close()
                raise PackageError("package command exceeds launch bound")
        managed = (job.launch(launch, env) if job is not None else subprocess.Popen(
            launch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **options))
        with managed as process:
            try:
                try:
                    if job is not None:
                        job.resume(process.pid)
                        _require(process.stdin.write(payload) == len(payload),
                                 "complete package launch input write is unconfirmed")
                        process.stdin.close()
                except BaseException:
                    process.kill()
                    process.wait(timeout=20)
                    if job is not None:
                        job.close()
                    raise
                output = [bytearray(), bytearray()]
                exceeded = threading.Event()
                guard = threading.Lock()
                def capture(stream, index):
                    while chunk := stream.read(65536):
                        with guard:
                            if sum(map(len, output)) + len(chunk) > _MAX_OUTPUT_BYTES:
                                exceeded.set()
                            elif not exceeded.is_set():
                                output[index].extend(chunk)
                readers = [threading.Thread(target=capture, args=(stream, index), daemon=True)
                           for index, stream in enumerate((process.stdout, process.stderr))]
                for reader in readers:
                    reader.start()
                deadline = time.monotonic() + timeout
                while process.poll() is None or any(reader.is_alive() for reader in readers):
                    if exceeded.is_set() or time.monotonic() >= deadline:
                        if os.name == "nt":
                            job.terminate()
                        else:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        process.wait(timeout=20)
                        for reader in readers:
                            reader.join(timeout=20)
                        _require(not any(reader.is_alive() for reader in readers),
                                 "package process/output termination is unconfirmed")
                        if job is not None:
                            job.close()
                        raise PackageError("package process exceeded time/output bound and was terminated")
                    time.sleep(0.01)
                _require(process.returncode == 0, "pinned package executor failed")
                if job is not None:
                    job.close()
            finally:
                if job is not None:
                    job.close()
                elif process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=20)
        return output[0].decode("utf-8")
    finally:
        if job is not None:
            job.close()


def _environment(profile: dict) -> dict:
    root = Path(profile["venv"])
    cfg = root / "pyvenv.cfg"
    _relative(cfg, root)
    raw = _read_bytes(cfg, 64 * 1024)
    values = dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)
    values = {key.strip().lower(): value.strip() for key, value in values.items()}
    _require(values.get("include-system-site-packages", "").lower() == "false",
             "system-site packages are outside this bounded operation")
    code = (
        "import json,sys; observed_prefix=sys.prefix; observed_exec_prefix=sys.exec_prefix; "
        "sys.prefix=sys.exec_prefix=sys.argv[1]; import sysconfig; "
        "print(json.dumps({'executable':sys.executable,'version':list(sys.version_info[:3]),"
        "'base_prefix':sys.base_prefix,'isolated_prefix':observed_prefix,"
        "'isolated_exec_prefix':observed_exec_prefix,'paths':sysconfig.get_paths(scheme='venv',"
        "vars={'base':sys.argv[1],'platbase':sys.argv[1],'installed_base':sys.argv[1],"
        "'installed_platbase':sys.argv[1]})}))"
    )
    # -S suppresses .pth/sitecustomize execution; this probe imports no provider.
    measured = json.loads(_run([profile["interpreter"], "-I", "-S", "-B", "-c", code, str(root)]))
    _require(os.path.abspath(measured["executable"]) == os.path.abspath(profile["interpreter"]),
             "executed interpreter differs from configured target")
    paths = {key: str(Path(measured["paths"][key])) for key in
             ("purelib", "platlib", "scripts", "include", "data")}
    for key, path in paths.items():
        _require(Path(path).is_relative_to(root), "Python install scheme escapes target: " + key)
    executable = Path(profile["interpreter"]).resolve(strict=True)
    return {"host": profile["host"], "interpreter": profile["interpreter"], "venv": str(root),
            "executable_sha256": hashlib.sha256(_read_bytes(executable)).hexdigest(),
            "pyvenv_cfg_sha256": hashlib.sha256(raw).hexdigest(), "paths": paths,
            "version": measured["version"], "base_prefix": measured["base_prefix"],
            "isolated_prefix": measured["isolated_prefix"],
            "isolated_exec_prefix": measured["isolated_exec_prefix"],
            "measurement": "isolated-no-site-interpreter-and-config-bytes",
            "scheme_authority": "derived-venv-scheme-from-configured-existing-PEP405-root",
            "transaction_mutex": str(_mutex_path(profile))}


def target_metadata(environment: dict) -> dict:
    """Bounded stat-only comparison: no arbitrary configuration/user contents."""
    root = Path(environment["venv"])
    result = {}
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            stat = path.lstat()
            result[path.relative_to(root).as_posix()] = [stat.st_mode, stat.st_size, stat.st_mtime_ns]
            _require(len(result) <= _MAX_FILES, "environment metadata exceeds bound")
    return result


def _entry_points(raw: str) -> list[dict]:
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string(raw)
    return [{"group": group, "name": name, "value": value}
            for group in config.sections() for name, value in config.items(group)]


def _wheel(item: dict, profile: dict, environment: dict, *, captured: bytes | None = None) -> dict:
    _require(set(item) == {"filename", "sha256", "distribution", "version", "component_ref",
                          "source_repository", "source_commit", "source_kind"}, "exact wheel descriptor required")
    filename = item["filename"]
    _require(isinstance(filename, str) and bool(_LEAF.fullmatch(filename))
             and filename.endswith(".whl"), "wheel must be a leaf filename")
    _require(bool(_SHA.fullmatch(str(item["sha256"])))
             and isinstance(item["source_repository"], str) and bool(item["source_repository"])
             and bool(_REF.fullmatch(str(item["component_ref"]))), "immutable wheel identity required")
    source = urlsplit(item["source_repository"])
    _require(source.scheme == "https" and bool(source.netloc) and source.username is None
             and source.password is None and not source.query and not source.fragment,
             "artifact provenance must contain no access material")
    _require((item["source_kind"] == "module-build"
              and bool(re.fullmatch(r"[0-9a-f]{40}", str(item["source_commit"]))))
             or (item["source_kind"] == "distribution-release" and item["source_commit"] is None),
             "module builds require a commit; release dependencies use their immutable artifact hash")
    _require(_name(item["distribution"]) != "pip", "this operation cannot replace its executor")
    root = Path(profile["artifact_root"])
    path = root / filename
    _relative(path, root)
    raw = _read_bytes(path) if captured is None else captured
    _require(len(raw) <= _MAX_WHEEL_BYTES and hashlib.sha256(raw).hexdigest() == item["sha256"],
             "wheel bytes differ from the declared immutable artifact")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        _require(len(names) == len(set(names)) and len(names) <= _MAX_FILES, "duplicate/oversized wheel")
        _require(sum(entry.file_size for entry in archive.infolist()) <= _MAX_EXPANDED_BYTES,
                 "wheel expanded bytes exceed bound")
        _require(all(entry.file_size <= _MAX_WHEEL_BYTES for entry in archive.infolist()),
                 "wheel member bytes exceed bound")
        for name in names:
            leaf = PurePosixPath(name)
            _require(not leaf.is_absolute() and ".." not in leaf.parts and "\\" not in name
                     and ":" not in name, "unsafe wheel member")
            mode = archive.getinfo(name).external_attr >> 16
            _require((mode & 0o170000) != 0o120000, "wheel symlinks are unsupported")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        _require(len(metadata_names) == 1, "one wheel distribution required")
        info = metadata_names[0].removesuffix("/METADATA")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        _require(_name(metadata["Name"]) == _name(item["distribution"])
                 and metadata["Version"] == item["version"], "wheel metadata identity differs")
        requires = metadata.get_all("Requires-Dist", [])
        _require(not any("@" in requirement for requirement in requires),
                 "direct-reference dependencies are outside the closed offline wheel set")
        record_name = info + "/RECORD"
        record = list(csv.reader(io.StringIO(archive.read(record_name).decode())))
        listed = set()
        for row in record:
            _require(len(row) == 3 and row[0] in names and row[0] not in listed, "invalid wheel RECORD")
            listed.add(row[0])
            data = archive.read(row[0])
            if row[0] != record_name:
                digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
                _require(row[1] == digest and row[2] == str(len(data)), "wheel RECORD hash differs")
        _require(listed == {name for name in names if not name.endswith("/")}, "wheel RECORD is incomplete")
        ep_name = info + "/entry_points.txt"
        points = _entry_points(archive.read(ep_name).decode()) if ep_name in names else []
        footprint = set()
        for name in listed:
            parts = PurePosixPath(name).parts
            if parts[0].endswith(".data"):
                _require(len(parts) >= 3 and parts[1] in {"purelib", "platlib", "scripts", "data"},
                         "unsupported wheel data scheme")
                key = parts[1]
                destination = Path(environment["paths"][key]).joinpath(*parts[2:])
            else:
                destination = Path(environment["paths"]["purelib"]).joinpath(*parts)
            footprint.add(_relative(destination, Path(environment["venv"])))
        for name in ("INSTALLER", "REQUESTED", "direct_url.json", "RECORD"):
            footprint.add(_relative(Path(environment["paths"]["purelib"]) / info / name,
                                    Path(environment["venv"])))
        for point in points:
            if point["group"] in {"console_scripts", "gui_scripts"}:
                _require(bool(_LEAF.fullmatch(point["name"])), "unsafe script entry point")
                suffixes = (".exe", "-script.py") if os.name == "nt" else ("",)
                for suffix in suffixes:
                    footprint.add(_relative(Path(environment["paths"]["scripts"]) / (point["name"] + suffix),
                                            Path(environment["venv"])))
    return {**item, "requires_dist": requires, "entry_points": points,
            "expanded_bytes": sum(entry.file_size for entry in archive.infolist()),
            "footprint": sorted(footprint)}


@contextlib.contextmanager
def _frozen_wheels(profile: dict, wheels: list[dict], environment: dict):
    """The executor consumes exactly the captured/validated artifact bytes."""
    _require(len(wheels) <= _MAX_FILES, "wheel closure exceeds count bound")
    with tempfile.TemporaryDirectory(prefix=".ocean-python-wheels-", dir=profile["artifact_root"]) as temporary:
        total = 0
        frozen = {**profile, "artifact_root": temporary}
        for wheel in wheels:
            original = {key: wheel[key] for key in (
                "filename", "sha256", "distribution", "version", "component_ref",
                "source_repository", "source_commit", "source_kind",
            )}
            path = Path(profile["artifact_root"]) / original["filename"]
            _relative(path, Path(profile["artifact_root"]))
            captured = _read_bytes(path)
            total += len(captured)
            _require(total <= _MAX_EXPANDED_BYTES, "wheel closure capture exceeds byte bound")
            _wheel(original, profile, environment, captured=captured)
            target = Path(temporary) / original["filename"]
            with target.open("xb") as file:
                file.write(captured)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(target, 0o400)
        yield frozen


def _script_paths(environment: dict, point: dict) -> list[Path]:
    _require(bool(_LEAF.fullmatch(point["name"])), "unsafe installed script entry point")
    root = Path(environment["paths"]["scripts"])
    suffixes = (".exe", "-script.py") if os.name == "nt" else ("",)
    return [root / (point["name"] + suffix) for suffix in suffixes]


def _inventory(environment: dict, *, skip: set[str] | None = None) -> tuple[list[dict], dict[str, list[str]]]:
    """Technical installed metadata and file owners; never execute site hooks."""
    root = Path(environment["venv"])
    site = Path(environment["paths"]["purelib"])
    _require(not any(site.glob("*.egg-info")) and not any(site.glob("*.egg"))
             and not any(site.glob("*.egg-link")) and not (site / "easy-install.pth").exists(),
             "legacy/editable distributions without complete RECORD ownership are unsupported")
    for editable in site.glob("__editable__*"):
        raise PackageError("PEP660 editable installation has no supported immutable wheel ownership")
    result, owners = [], {}
    seen = set()
    total_bytes = 0
    for directory in sorted(site.glob("*.dist-info")):
        if _relative(directory, root) in (skip or set()):
            continue
        _relative(directory, root)
        captured = {}
        for leaf in ("METADATA", "RECORD", "entry_points.txt", "direct_url.json"):
            path = directory / leaf
            if path.exists():
                captured[leaf] = _read_bytes(path, _MAX_METADATA_BYTES)
                total_bytes += len(captured[leaf])
        _require(total_bytes <= _MAX_EXPANDED_BYTES and len(result) < _MAX_FILES,
                 "installed metadata exceeds bound")
        _require({"METADATA", "RECORD"}.issubset(captured),
                 "installed distribution has no complete metadata/RECORD contract")
        metadata = BytesParser().parsebytes(captured["METADATA"])
        _require(isinstance(metadata["Name"], str) and isinstance(metadata["Version"], str),
                 "installed distribution identity is missing")
        _require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", metadata["Name"]))
                 and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]{0,127}", metadata["Version"])),
                 "unsupported installed distribution identity")
        if "direct_url.json" in captured:
            direct = json.loads(captured["direct_url.json"])
            _require(not direct.get("dir_info", {}).get("editable", False),
                     "PEP660 editable installation has no supported immutable wheel ownership")
        name = _name(metadata["Name"])
        _require(name not in seen, "multiple installed distributions share a selected name")
        seen.add(name)
        requires = metadata.get_all("Requires-Dist", [])
        _require(not any("@" in requirement for requirement in requires),
                 "installed direct-reference dependency is unsupported by this offline operation")
        rows = list(csv.reader(io.StringIO(captured["RECORD"].decode("utf-8"))))
        files = []
        for row in rows:
            _require(len(row) == 3, "invalid installed RECORD")
            relative = _relative(directory.parent / row[0], root)
            path = root / relative
            _require(path.is_file(), "installed RECORD points at a missing file")
            _require(relative not in files, "installed RECORD duplicates a path")
            files.append(relative)
            owners.setdefault(os.path.normcase(relative), []).append(name)
        _require(len(owners) <= _MAX_FILES, "installed ownership exceeds bound")
        # Every technical DistInfo file must be represented. Unrecorded legacy
        # files are a repair gate; the operation never guesses an old footprint.
        for current, directories, leaves in os.walk(directory, followlinks=False):
            _require(not any((Path(current) / child).is_symlink() for child in directories),
                     "installed metadata directory contains a symlink")
            for leaf in leaves:
                _require(_relative(Path(current) / leaf, root) in files,
                         "installed DistInfo contains an unrecorded file")
        points = _entry_points(captured["entry_points.txt"].decode()) if "entry_points.txt" in captured else []
        for point in points:
            if point["group"] in {"console_scripts", "gui_scripts"}:
                existing = [path for path in _script_paths(environment, point) if path.is_file()]
                _require(bool(existing) and all(_relative(path, root) in files for path in existing),
                         "installed entry point has a missing or incomplete script RECORD")
        result.append({"distribution": name, "version": metadata["Version"],
                       "dist_info": _relative(directory, root), "files": sorted(files),
                       "entry_points": points, "requires_dist": requires,
                       "metadata_sha256": {leaf: hashlib.sha256(data).hexdigest()
                                           for leaf, data in captured.items()},
                       "direct_url_sha256": hashlib.sha256(captured["direct_url.json"]).hexdigest()
                       if "direct_url.json" in captured else None})
    return sorted(result, key=lambda row: row["distribution"]), {
        path: sorted(value) for path, value in sorted(owners.items())}


def _installed(environment: dict, names: set[str], inventory=None) -> tuple[list[dict], set[str]]:
    rows, _owners = inventory if inventory is not None else _inventory(environment)
    selected = [deepcopy(row) for row in rows if row["distribution"] in names]
    root = Path(environment["venv"])
    owned = set()
    total = 0
    for distribution in selected:
        directory = root / distribution["dist_info"]
        for row in csv.reader(io.StringIO(_read_bytes(directory / "RECORD", _MAX_METADATA_BYTES).decode())):
            relative = _relative(directory.parent / row[0], root)
            data = _read_bytes(root / relative)
            total += len(data)
            _require(total <= _MAX_EXPANDED_BYTES, "selected beforestate bytes exceed bound")
            if row[1]:
                algorithm, _, value = row[1].partition("=")
                _require(algorithm in hashlib.algorithms_available, "unsupported installed RECORD digest")
                observed = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).decode().rstrip("=")
                _require(observed == value, "installed RECORD bytes changed")
            if row[2]:
                _require(int(row[2]) == len(data), "installed RECORD size changed")
            owned.add(relative)
    return selected, owned


def _file_state(root: Path, footprint: set[str]) -> dict:
    result = {}
    for relative in sorted(footprint):
        _require(isinstance(relative, str), "invalid package footprint")
        path = root / relative
        _require(_relative(path, root) == relative, "noncanonical package footprint")
        if path.exists():
            _require(path.is_file(), "package footprint is not a regular file")
            raw = _read_bytes(path)
            result[relative] = {"sha256": hashlib.sha256(raw).hexdigest(),
                                "mode": path.stat().st_mode & 0o777, "mtime_ns": path.stat().st_mtime_ns}
        else:
            result[relative] = None
    return result


def _directories(root: Path, footprint: set[str]) -> dict:
    parents = {parent for relative in footprint for parent in (root / relative).parents
               if parent.is_relative_to(root)}
    result = {}
    for path in sorted(parents):
        relative = path.relative_to(root).as_posix()
        _require(not path.is_symlink(), "package directory is a symlink")
        if path.exists():
            _require(path.is_dir(), "package parent is not a directory")
            stat = path.stat()
            result[relative] = {"mode": stat.st_mode & 0o777, "mtime_ns": stat.st_mtime_ns}
        else:
            result[relative] = None
    return result


def _pip(environment: dict, profile: dict, wheels: list[dict], *, dry_run: bool,
         inventory: list[dict] | None = None, check: bool = False) -> list[str]:
    # Restore only PEP405's measured prefix and selected site path. Suppressing
    # site initialization prevents arbitrary editable .pth/provider execution.
    bootstrap = (
        "import runpy,sys,os,hashlib; root=sys.argv.pop(1); site=sys.argv.pop(1); "
        "from pathlib import Path; "
        "\nif os.name!='nt':"
        "\n import fcntl; fd=int(os.environ['OCEAN_PACKAGE_LOCK_FD']); "
        "path=Path(root).parent/('.ocean-python-'+hashlib.sha256(os.path.normcase(root).encode()).hexdigest()+'.lock'); "
        "a=os.fstat(fd); b=path.stat(); assert (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino); "
        "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)"
        "\n"
        "sys.prefix=sys.exec_prefix=root; sys.path.append(site); "
        "import importlib.util,pathlib; spec=importlib.util.find_spec('pip'); "
        "assert spec and pathlib.Path(spec.origin)==pathlib.Path(site)/'pip'/'__init__.py'; "
        "sys.argv[0]='pip'; runpy.run_module('pip',run_name='__main__')"
    )
    command = [profile["interpreter"], "-I", "-S", "-B", "-c", bootstrap,
               environment["venv"], environment["paths"]["purelib"], "--disable-pip-version-check",
               "--no-input", "--no-cache-dir"]
    if check:
        return command + ["check"]
    command.extend(["install", "--no-index", "--no-compile", "--only-binary=:all:", "--quiet"])
    if dry_run:
        command.extend(["--dry-run", "--report", "-"])
        changed = {_name(wheel["distribution"]) for wheel in wheels}
        # Asking the native resolver to retain every unrelated installed pin
        # makes its Requires-Dist constraints participate, including reverse deps.
        command.extend(row["distribution"] + "==" + row["version"]
                       for row in inventory or [] if row["distribution"] not in changed)
    else:
        command.extend(["--no-deps", "--force-reinstall"])
    command.extend(str(Path(profile["artifact_root"]) / wheel["filename"]) for wheel in wheels)
    return command


@_serialized
def prepare_package_plan(request: dict, components: set[str]) -> dict:
    _require(set(request) == {"profile_id", "profile_sha256", "wheels", "required_entry_points"},
             "package request accepts identities, never free target paths")
    profile_raw, profile = _profile(request["profile_id"], request["profile_sha256"])
    environment = _environment(profile)
    _require(isinstance(request["wheels"], list) and bool(request["wheels"]), "nonempty wheel closure required")
    wheels = [_wheel(item, profile, environment) for item in request["wheels"]]
    _require(sum(item["expanded_bytes"] for item in wheels) <= _MAX_EXPANDED_BYTES,
             "wheel closure expanded bytes exceed bound")
    names = [_name(item["distribution"]) for item in wheels]
    _require(len(names) == len(set(names)), "duplicate wheel distribution")
    refs = sorted({item["component_ref"] for item in wheels})
    _require(set(refs).issubset(components), "wheel operation exceeds approved component scope")
    _require({item["component_ref"] for item in wheels if item["source_kind"] == "module-build"} == set(refs),
             "each package component requires its own declared module build")
    inventory = _inventory(environment)
    installed, owned = _installed(environment, set(names), inventory)
    executor, _ = _installed(environment, {"pip"}, inventory)
    _require(len(executor) == 1, "existing recorded pip executor required")
    executor[0]["file_state"] = _file_state(Path(environment["venv"]), set(executor[0]["files"]))
    footprint = owned | {path for item in wheels for path in item["footprint"]}
    _require(all(set(inventory[1].get(os.path.normcase(path), [])) <= set(names) for path in footprint),
             "wheel footprint has another installed distribution owner")
    before_files = _file_state(Path(environment["venv"]), footprint)
    _require(all(state is None or path in owned for path, state in before_files.items()),
             "wheel would overwrite an unowned existing file")
    required = request["required_entry_points"]
    _require(isinstance(required, list), "required entry points must be a list")
    available = [{"distribution": _name(wheel["distribution"]), **point}
                 for wheel in wheels for point in wheel["entry_points"]]
    _require(all(isinstance(point, dict) and set(point) == {"distribution", "group", "name", "value"}
                 and point in available for point in required), "required entry point missing from wheel")
    metadata_before = target_metadata(environment)
    _run(_pip(environment, profile, [], dry_run=False, check=True))
    with _frozen_wheels(profile, wheels, environment) as frozen:
        report = json.loads(_run(_pip(environment, frozen, wheels, dry_run=True, inventory=inventory[0])))
    _require(target_metadata(environment) == metadata_before, "read-only package resolution mutated environment")
    observed = {(_name(item["metadata"]["name"]), item["metadata"]["version"],
                 item["download_info"]["archive_info"]["hashes"]["sha256"])
                for item in report.get("install", [])}
    expected = {(_name(item["distribution"]), item["version"], item["sha256"]) for item in wheels}
    _require(observed == expected, "native pip resolution differs from complete pinned wheel closure")
    _require(_file_state(Path(environment["venv"]), footprint) == before_files,
             "package beforestate changed during planning")
    _require(_inventory(environment) == inventory, "installed dependency/owner inventory changed during planning")
    _require(_profile(request["profile_id"], request["profile_sha256"])[0] == profile_raw,
             "profile changed during planning")
    for item in wheels:
        _wheel({key: item[key] for key in request["wheels"][0]}, profile, environment)
    return _with_hash({"schema": PLAN_SCHEMA, "request": request, "environment": environment,
                       "component_refs": refs, "wheels": sorted(wheels, key=lambda row: _name(row["distribution"])),
                       "executor": executor[0], "before": {"distributions": installed, "files": before_files,
                                                             "inventory": inventory[0], "owners": inventory[1],
                                                              "target_metadata": metadata_before,
                                                             "directories": _directories(Path(environment["venv"]), footprint)},
                       "checks": {check: "SUCCESS" for check in sorted(CHECKS)}})


@_serialized
def validate_package_plan(plan: dict, components: set[str]) -> dict:
    _require(isinstance(plan, dict) and plan.get("schema") == PLAN_SCHEMA
             and plan.get("content_hash") == canonical_hash({key: value for key, value in plan.items()
                                                            if key != "content_hash"}), "package plan hash differs")
    actual = prepare_package_plan(plan["request"], components)
    _require(actual == plan, "fresh package plan/environment/beforestate differs from approved payload")
    return actual


@_serialized
def package_target_state(plan: dict) -> dict:
    _, profile = _profile(plan["request"]["profile_id"], plan["request"]["profile_sha256"])
    environment = _environment(profile)
    _require(environment == plan["environment"], "package environment identity changed")
    return target_metadata(environment)


def _atomic(path: Path, value: dict) -> None:
    raw = bounded_json(value)
    _require(len(raw) <= _MAX_EXPANDED_BYTES and not path.is_symlink(), "unsafe or oversized journal")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".python-packages-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _transaction_entry(plan: dict) -> dict:
    return {"type": "python-packages", "ref": plan["component_refs"][0],
            "id": plan["request"]["profile_id"], "dest": plan["environment"]["venv"],
            "package_plan_hash": plan["content_hash"], "component_refs": plan["component_refs"]}


def _store_receipt(path: Path, value: dict, *, activation_log: bool = False) -> None:
    if not activation_log:
        _atomic(path, value)
        return
    log = (_json_bytes(path)[1] if path.exists() else
           {"schema": "ellmos.open-ocean-activation-log.v1", "entries": []})
    _require(log.get("schema") == "ellmos.open-ocean-activation-log.v1"
             and isinstance(log.get("entries"), list), "unsupported package activation journal")
    seed = {"type": "python-packages", "ref": value["component_refs"][0],
            "id": value["profile_id"], "dest": value["environment"]["venv"],
            "package_plan_hash": value["plan_hash"], "component_refs": value["component_refs"]}
    old = [entry for entry in log["entries"] if entry.get("type") == "python-packages"]
    _require(len(old) <= 1 and all({key: row.get(key) for key in seed} == seed for row in old),
             "another package transaction already owns this journal")
    log["entries"] = [entry for entry in log["entries"] if entry.get("type") != "python-packages"]
    log["entries"].append({**seed, "transaction": value})
    _atomic(path, log)


def _load_receipt(path: Path, plan: dict) -> tuple[dict, bool]:
    _, value = _json_bytes(path)
    if value.get("schema") == "ellmos.open-ocean-activation-log.v1":
        entries = value.get("entries")
        _require(isinstance(entries, list), "package activation entries missing")
        found = [entry for entry in entries if entry.get("type") == "python-packages"]
        _require(len(found) == 1 and set(found[0]) == set(_transaction_entry(plan)) | {"transaction"}
                 and {key: found[0][key] for key in _transaction_entry(plan)} == _transaction_entry(plan),
                 "exact embedded package transaction is missing")
        return found[0]["transaction"], True
    return value, False


@_serialized
def apply_package_plan(plan: dict, receipt_path: Path, components: set[str], *,
                       activation_log: bool = False) -> dict:
    validate_package_plan(plan, components)
    if activation_log and receipt_path.exists():
        _, existing = _json_bytes(receipt_path)
        _require(not any(entry.get("type") == "python-packages" for entry in existing.get("entries", [])),
                 "package transaction already exists; never replay")
    else:
        _require(not receipt_path.exists(), "package transaction receipt already exists")
    root = Path(plan["environment"]["venv"])
    _require(not receipt_path.resolve(strict=False).is_relative_to(root), "journal must be outside target environment")
    backup = {}
    for relative, expected in plan["before"]["files"].items():
        if expected is not None:
            raw = _read_bytes(root / relative)
            _require(hashlib.sha256(raw).hexdigest() == expected["sha256"], "beforestate changed before snapshot")
            backup[relative] = base64.b64encode(raw).decode()
    receipt = {"schema": RECEIPT_SCHEMA, "plan_hash": plan["content_hash"],
               "environment": plan["environment"], "component_refs": plan["component_refs"],
               "profile_id": plan["request"]["profile_id"],
               "before": plan["before"], "backup": backup, "state": "applying"}
    _, profile = _profile(plan["request"]["profile_id"], plan["request"]["profile_sha256"])
    with _frozen_wheels(profile, plan["wheels"], plan["environment"]) as frozen:
        # The one authoritative journal already contains rollback bytes when
        # the executor starts. Finalization updates this same file atomically.
        _store_receipt(receipt_path, _with_hash(receipt), activation_log=activation_log)
        validate_package_plan(plan, components)
        failure = None
        try:
            _run(_pip(plan["environment"], frozen, plan["wheels"], dry_run=False))
            _run(_pip(plan["environment"], profile, [], dry_run=False, check=True))
        except PackageError as exc:
            failure = exc
    footprint = set(plan["before"]["files"])
    try:
        installed, owned = _installed(plan["environment"], {_name(row["distribution"]) for row in plan["wheels"]})
        _require(owned.issubset(footprint), "executor wrote unplanned installed RECORD paths")
    except (PackageError, OSError, ValueError, KeyError):
        installed = []
        failure = failure or PackageError("installed metadata is incomplete; captured footprint requires recovery")
    receipt.update(after={"distributions": installed, "files": _file_state(root, footprint),
                          "directories": _directories(root, footprint)},
                   state="apply-failed" if failure else "applied")
    result = _with_hash(receipt)
    _store_receipt(receipt_path, result, activation_log=activation_log)
    if failure:
        raise failure
    verify_package_receipt(plan, receipt_path, components)
    return {"state": "applied", "plan_hash": plan["content_hash"],
            "receipt_sha256": hashlib.sha256(_read_bytes(receipt_path, _MAX_EXPANDED_BYTES)).hexdigest(),
            "installed": installed, "checks": {key: "SUCCESS" for key in
                                                ("distribution", "record", "provenance", "entry-points")}}


def _receipt(plan: dict, path: Path, components: set[str]) -> dict:
    _require(plan.get("schema") == PLAN_SCHEMA
             and plan.get("content_hash") == canonical_hash({key: item for key, item in plan.items()
                                                            if key != "content_hash"}), "package plan hash differs")
    _require(set(plan["component_refs"]).issubset(components), "package receipt exceeds component scope")
    value, _embedded = _load_receipt(path, plan)
    _require(value.get("schema") == RECEIPT_SCHEMA and value.get("plan_hash") == plan["content_hash"]
             and value.get("environment") == plan["environment"] and value.get("before") == plan["before"]
             and value.get("component_refs") == plan["component_refs"]
             and value.get("content_hash") == canonical_hash({key: item for key, item in value.items()
                                                             if key != "content_hash"}), "package receipt binding differs")
    package_target_state(plan)
    return value


def _complete_afterstate(plan: dict) -> dict:
    root = Path(plan["environment"]["venv"])
    installed, owned = _installed(plan["environment"], {_name(row["distribution"]) for row in plan["wheels"]})
    _require(owned.issubset(set(plan["before"]["files"])),
             "executor wrote unplanned installed RECORD paths")
    _require({(row["distribution"], row["version"]) for row in installed}
             == {(_name(row["distribution"]), row["version"]) for row in plan["wheels"]},
             "required distributions are not installed")
    _, profile = _profile(plan["request"]["profile_id"], plan["request"]["profile_sha256"])
    _run(_pip(plan["environment"], profile, [], dry_run=False, check=True))
    inventory = _inventory(plan["environment"])[0]
    changed = {_name(row["distribution"]) for row in plan["wheels"]}
    _require([row for row in inventory if row["distribution"] not in changed]
             == [row for row in plan["before"]["inventory"] if row["distribution"] not in changed],
             "unselected installed distribution/requirements/ownership changed")
    for wheel in plan["wheels"]:
        row = next(item for item in installed if item["distribution"] == _name(wheel["distribution"]))
        observed = next(item for item in inventory if item["distribution"] == row["distribution"])
        direct_raw = _read_bytes(root / row["dist_info"] / "direct_url.json", _MAX_METADATA_BYTES)
        _require(hashlib.sha256(direct_raw).hexdigest()
                 == observed["direct_url_sha256"] == row["direct_url_sha256"],
                 "installed wheel provenance changed after inventory capture")
        direct = json.loads(direct_raw)
        _require(direct.get("archive_info", {}).get("hashes", {}).get("sha256") == wheel["sha256"],
                 "installed wheel provenance differs")
        _wheel({key: wheel[key] for key in plan["request"]["wheels"][0]}, profile, plan["environment"])
    available = [{"distribution": row["distribution"], **point}
                 for row in installed for point in row["entry_points"]]
    _require(all(point in available for point in plan["request"]["required_entry_points"]),
             "required installed entry point is missing")
    return {"distributions": installed,
            "files": _file_state(root, set(plan["before"]["files"])),
            "directories": _directories(root, set(plan["before"]["files"]))}


@_serialized
def verify_package_receipt(plan: dict, path: Path, components: set[str]) -> dict:
    value = _receipt(plan, path, components)
    _require(value["state"] == "applied", "package transaction is not a completed apply")
    after = _complete_afterstate(plan)
    _require(after == value["after"], "installed package afterstate drifted")
    return {"schema": "ellmos.ocean.python-packages.verification.v1", "status": "verified",
            "plan_hash": plan["content_hash"], "installed": after["distributions"],
            "receipt_sha256": hashlib.sha256(_read_bytes(path, _MAX_EXPANDED_BYTES)).hexdigest(),
            "runtime_verified": False, "checks": {key: "SUCCESS" for key in
                                                   ("distribution", "record", "provenance", "entry-points")}}


def _recovery_backup(plan: dict, value: dict) -> None:
    expected = {path for path, state in plan["before"]["files"].items() if state is not None}
    _require(set(value.get("backup", {})) == expected, "recovery backup scope differs")
    total = 0
    for relative in expected:
        data = base64.b64decode(value["backup"][relative], validate=True)
        total += len(data)
        _require(total <= _MAX_EXPANDED_BYTES
                 and hashlib.sha256(data).hexdigest() == plan["before"]["files"][relative]["sha256"],
                 "recovery backup bytes differ")


def _recovery_target(plan: dict) -> dict:
    environment = plan["environment"]
    root = Path(environment["venv"])
    footprint = set(plan["before"]["files"])
    allowed = footprint | set(plan["before"]["directories"])
    original = plan["before"].get("target_metadata")
    _require(isinstance(original, dict) and bool(original), "full target baseline required for recovery")
    current = target_metadata(environment)
    _require({p: row for p, row in current.items() if p not in allowed}
             == {p: row for p, row in original.items() if p not in allowed},
             "recovery target changed outside approved footprint")
    _require(_file_state(root, set(plan["executor"]["files"])) == plan["executor"]["file_state"],
             "recovery package executor changed")
    changed = {_name(wheel["distribution"]) for wheel in plan["wheels"]}
    skip = {row["dist_info"] for row in plan["before"]["inventory"]
            if row["distribution"] in changed}
    for relative in footprint:
        parts = PurePosixPath(relative).parts
        for i, part in enumerate(parts):
            if part.endswith(".dist-info"):
                skip.add(PurePosixPath(*parts[:i + 1]).as_posix())
    inventory, owners = _inventory(environment, skip=skip)
    _require(inventory == [row for row in plan["before"]["inventory"]
                           if row["distribution"] not in changed],
             "recovery unselected distribution inventory changed")
    expected_owners = {path: [owner for owner in row if owner not in changed]
                       for path, row in plan["before"]["owners"].items()}
    expected_owners = {path: row for path, row in expected_owners.items() if row}
    _require(owners == expected_owners, "recovery unselected ownership changed")
    return {"target_metadata": current, "files": _file_state(root, footprint),
            "directories": _directories(root, footprint), "unselected_inventory": inventory,
            "unselected_owners": owners}


@_serialized
def inspect_package_recovery(plan: dict, path: Path, components: set[str]) -> dict:
    """No package/journal writes: capture an explicit recovery CAS, never guess."""
    original = _read_bytes(path, _MAX_EXPANDED_BYTES)
    value = _receipt(plan, path, components)
    _require(value["state"] in {"applying", "applied", "apply-failed", "rolling-back"},
             "package journal has no recoverable transaction")
    _recovery_backup(plan, value)
    observed = _recovery_target(plan)
    try:
        complete = _complete_afterstate(plan)
    except PackageError:
        complete = None
    # Measurement itself must not change targets, profile, executor or journal.
    _require(_recovery_target(plan) == observed
             and _read_bytes(path, _MAX_EXPANDED_BYTES) == original,
             "recovery inputs changed during capture")
    return _with_hash({"schema": "ellmos.ocean.python-packages.recovery.v1",
                       "plan_hash": plan["content_hash"],
                       "journal_sha256": hashlib.sha256(original).hexdigest(),
                       "profile_id": plan["request"]["profile_id"],
                       "profile_sha256": plan["request"]["profile_sha256"],
                       "state": value["state"], "observed": observed,
                       "complete_afterstate": complete, "runtime_verified": False})


@_serialized
def reconcile_package_receipt(plan: dict, path: Path, components: set[str], evidence: dict) -> dict:
    """Finalize only a fully measured afterstate; execute no pip or target writes."""
    current = inspect_package_recovery(plan, path, components)
    _require(evidence == current and current["complete_afterstate"] is not None,
             "complete bound recovery evidence required")
    value, embedded = _load_receipt(path, plan)
    history = list(value.get("recovery_history", []))
    _require(len(history) < 100, "recovery history exceeds bound")
    history.append({"operation": "reconcile", "previous_state": value["state"],
                    "previous_receipt_hash": value["content_hash"], "evidence": current})
    value.update(state="applied", after=current["complete_afterstate"],
                 reconciliation_hash=current["content_hash"], recovery_history=history)
    _require(hashlib.sha256(_read_bytes(path, _MAX_EXPANDED_BYTES)).hexdigest()
             == current["journal_sha256"], "reconciliation journal CAS changed")
    _store_receipt(path, _with_hash({k: v for k, v in value.items() if k != "content_hash"}),
                   activation_log=embedded)
    return verify_package_receipt(plan, path, components)


@_serialized
def preflight_package_rollback(plan: dict, path: Path, components: set[str], *, recovery: dict | None = None) -> dict:
    value = _receipt(plan, path, components)
    if recovery is not None:
        _require(recovery == inspect_package_recovery(plan, path, components),
                 "explicit recovery snapshot CAS changed")
    else:
        _require(value["state"] in {"applied", "apply-failed"},
                 "interrupted package state requires explicit recovery evidence")
    root = Path(plan["environment"]["venv"])
    if recovery is None:
        _require(_file_state(root, set(plan["before"]["files"])) == value["after"]["files"],
                 "package rollback CAS differs from recorded afterstate")
        _require(_directories(root, set(plan["before"]["files"])) == value["after"]["directories"],
                 "package rollback directory CAS differs from recorded afterstate")
    for relative, expected in plan["before"]["files"].items():
        if expected is not None:
            data = base64.b64decode(value["backup"][relative], validate=True)
            _require(hashlib.sha256(data).hexdigest() == expected["sha256"], "rollback snapshot is corrupted")
    return value


@_serialized
def rollback_package_plan(plan: dict, path: Path, components: set[str], *, recovery: dict | None = None) -> dict:
    value = preflight_package_rollback(plan, path, components, recovery=recovery)
    root = Path(plan["environment"]["venv"])
    # Recheck the entire footprint before the first reverse operation.
    preflight_package_rollback(plan, path, components, recovery=recovery)
    _, embedded = _load_receipt(path, plan)
    history = list(value.get("recovery_history", []))
    _require(len(history) < 100, "recovery history exceeds bound")
    history.append({"operation": "rollback", "previous_state": value["state"],
                    "previous_receipt_hash": value["content_hash"],
                    "previous_journal_sha256": hashlib.sha256(_read_bytes(path, _MAX_EXPANDED_BYTES)).hexdigest(),
                    "evidence": recovery})
    value["state"] = "rolling-back"
    value["recovery_history"] = history
    if recovery is not None:
        value["recovery_hash"] = recovery["content_hash"]
    _store_receipt(path, _with_hash({k: v for k, v in value.items() if k != "content_hash"}),
                   activation_log=embedded)
    for relative, expected in plan["before"]["files"].items():
        target = root / relative
        if expected is None:
            if target.exists():
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = base64.b64decode(value["backup"][relative], validate=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".rollback-", dir=target.parent)
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
            os.chmod(temporary, expected["mode"])
            os.replace(temporary, target)
            os.utime(target, ns=(target.stat().st_atime_ns, expected["mtime_ns"]))
    for relative, expected in sorted(plan["before"]["directories"].items(),
                                     key=lambda item: len(PurePosixPath(item[0]).parts), reverse=True):
        target = root / relative
        if expected is None:
            if target.exists():
                target.rmdir()
        else:
            os.chmod(target, expected["mode"])
            os.utime(target, ns=(target.stat().st_atime_ns, expected["mtime_ns"]))
    _require(_file_state(root, set(plan["before"]["files"])) == plan["before"]["files"],
             "restored package files differ from beforestate")
    restored, _ = _installed(plan["environment"], {_name(row["distribution"]) for row in plan["wheels"]})
    _require(restored == plan["before"]["distributions"], "restored distributions differ from beforestate")
    _require(_inventory(plan["environment"]) == (plan["before"]["inventory"], plan["before"]["owners"]),
             "restored complete installed inventory differs from beforestate")
    _require(target_metadata(plan["environment"]) == plan["before"]["target_metadata"],
             "restored complete target metadata differs from beforestate")
    _, profile = _profile(plan["request"]["profile_id"], plan["request"]["profile_sha256"])
    _run(_pip(plan["environment"], profile, [], dry_run=False, check=True))
    value["state"] = "rolled-back"
    _, embedded = _load_receipt(path, plan)
    _store_receipt(path, _with_hash({key: item for key, item in value.items() if key != "content_hash"}),
                   activation_log=embedded)
    return {"status": "rolled-back", "plan_hash": plan["content_hash"], "beforestate_restored": True}
