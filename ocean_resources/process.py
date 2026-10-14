"""Explicit owned-process adapter with application-verified checkpoint protocol.

No process is discovered/adopted by PID, no existing queue is edited, and this
adapter does not grant real resource admission. Its caller supplies the existing
arbiter and a separately authorized immutable command specification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock
import time
from typing import Callable
import uuid

from tools import windows_job
from tools.runtime_supervisor import (
    _capture_posix_process_fence,
    _posix_group_empty,
    _reap_unassigned_child,
    _terminate_child,
    _terminate_unfenced_posix_child,
)

from .adapters import ComputeExecutorAdapter
from .arbiter import HostLocalArbiter
from .contracts import Checkpoint, ExitReadback, Grant, Hold, SlotRequest, identity, instant

PROTOCOL = "ocean-owned-process.v1"

# Isolated interpreter startup cannot import sitecustomize or application code.
# No application (and therefore no helper) runs until its process group is fenced.
_POSIX_BOOTSTRAP = """
import os, select, sys
fd = int(sys.argv[1])
if not select.select([fd], [], [], 30)[0] or os.read(fd, 1) != b'G':
    raise SystemExit(125)
os.close(fd)
os.execve(sys.argv[2], sys.argv[2:], dict(os.environ))
"""


def _local_directory(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or not path.is_dir() or path.resolve() != path.absolute():
        raise ValueError("existing unlinked absolute local directory required")
    if path.drive.startswith("\\\\") or any(p.lower().startswith("onedrive") for p in path.parts):
        raise ValueError("process state/work directories must be host-local")
    return path


@dataclass(frozen=True)
class ProcessCommand:
    argv: tuple[str, ...]
    cwd: Path
    # Every executable/application input pin is explicit. No ambient source discovery.
    source_pins: tuple[tuple[Path, str], ...]
    environment: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if (
            not isinstance(self.argv, tuple)
            or not self.argv
            or any(not isinstance(a, str) or not a or "\x00" in a or len(a) > 8192 for a in self.argv)
            or sum(len(a) for a in self.argv) > 24000
        ):
            raise ValueError("explicit bounded immutable argv required")
        _local_directory(self.cwd)
        executable = Path(self.argv[0])
        if not executable.is_absolute() or not executable.is_file() or executable.is_symlink():
            raise ValueError("explicit existing executable required")
        if not isinstance(self.source_pins, tuple) or not self.source_pins:
            raise ValueError("explicit source pins required")
        for path, digest in self.source_pins:
            if (
                not isinstance(path, Path)
                or not path.is_absolute()
                or path.is_symlink()
                or path.resolve() != path.absolute()
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ValueError("invalid exact source pin")
        if executable not in {path for path, _ in self.source_pins}:
            raise ValueError("the executable itself must be pinned")
        if (
            not isinstance(self.environment, tuple)
            or any(
                not isinstance(k, str) or not k or "=" in k or "\x00" in k or k == "OCEAN_RESOURCE_RUN_DIR"
                or not isinstance(v, str) or "\x00" in v
                for k, v in self.environment
            )
            or len(dict(self.environment)) != len(self.environment)
        ):
            raise ValueError("explicit immutable environment required")
        if sum(len(k) + len(v) for k, v in self.environment) > 16000:
            raise ValueError("process environment exceeds bound")

    def verify_sources(self):
        for path, digest in self.source_pins:
            calculated = hashlib.sha256()
            if path.is_symlink() or not path.is_file():
                raise Hold("pinned process source changed or unavailable")
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    calculated.update(block)
            if calculated.hexdigest() != digest:
                raise Hold("pinned process source changed or unavailable")

    def fingerprint(self) -> str:
        """Bind the fixed command; the protocol run-directory variable is dynamic."""
        content = json.dumps({"argv": self.argv, "cwd": str(self.cwd),
                              "source_pins": [(str(p), h) for p, h in self.source_pins],
                              "environment": self.environment}, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        return hashlib.sha256(content).hexdigest()


@dataclass
class _Execution:
    grant: Grant
    identity: str
    directory: Path
    child: subprocess.Popen
    fence: dict | None
    job: int | None
    accepted: Checkpoint | None = None
    exited: bool = False


class OwnedProcessExecutor:
    """New explicitly configured children only; application owns checkpoint meaning.

    The worker reads start.json from OCEAN_RESOURCE_RUN_DIR, acknowledges ready.json,
    and on checkpoint.request.json writes a quiescent checkpoint.json with the same
    grant/execution identity and an application payload. A trusted application
    validator must approve that payload before any stop. Cooperative workers must
    not escape their owned job/process group or continue after acknowledging quiescence.
    """

    def __init__(
        self,
        arbiter: HostLocalArbiter,
        command: ProcessCommand,
        state_directory: Path,
        validate_checkpoint: Callable[[dict], bool],
        *,
        timeout_seconds: float = 5.0,
    ):
        if not instant(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError("bounded lifecycle timeout required")
        if not callable(validate_checkpoint):
            raise ValueError("application checkpoint validator required")
        self.arbiter, self.command = arbiter, command
        self.state_directory = _local_directory(state_directory)
        self.validator, self.timeout = validate_checkpoint, timeout_seconds
        self._executions: dict[Grant, _Execution] = {}
        self._mutex = RLock()
        self._pid = os.getpid()

    def _require_process(self):
        if os.getpid() != self._pid:
            raise Hold("foreign owned-executor process")

    def adapter(self) -> ComputeExecutorAdapter:
        return ComputeExecutorAdapter(self.start, self.checkpoint, self.stop, self.readback,
                                      self.command.fingerprint(), "cpu-owned-process")

    @staticmethod
    def _write(path: Path, payload: dict):
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        data = json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")
        if len(data) > 1024 * 1024:
            raise Hold("lifecycle message exceeds bound")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    @staticmethod
    def _message(path: Path) -> dict | None:
        if not path.exists():
            return None
        if path.is_symlink():
            raise Hold("linked worker response refused")
        with path.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise Hold("worker response exceeds bound")

        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise Hold("duplicate worker response key")
                value[key] = item
            return value

        def reject_constant(value):
            raise Hold("nonfinite worker response")

        value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
        if not isinstance(value, dict):
            raise Hold("worker response must be an object")
        return value

    def _execution(self, grant: Grant, execution_identity: str) -> _Execution:
        self.arbiter.request_for(grant)
        run = self._executions.get(grant)
        if run is None or run.identity != execution_identity:
            raise Hold("unknown owned execution")
        return run

    def _wait_message(self, run: _Execution, name: str) -> dict:
        deadline = time.monotonic() + self.timeout
        while True:
            value = self._message(run.directory / name)
            if value is not None:
                if (
                    value.get("schema") != PROTOCOL
                    or value.get("execution_identity") != run.identity
                    or value.get("grant") != asdict(run.grant)
                ):
                    raise Hold("worker response belongs to another execution")
                return value
            if time.monotonic() >= deadline:
                raise Hold("owned worker lifecycle acknowledgement timed out")
            time.sleep(0.02)

    def start(self, grant: Grant, request: SlotRequest, checkpoint: Checkpoint | None, execution_identity: str) -> bool:
        self._require_process()
        with self._mutex:
            self.arbiter.require_running(grant)
            identity(execution_identity)
            if request != self.arbiter.request_for(grant) or grant in self._executions:
                raise Hold("inconsistent or already-started execution")
            if self.arbiter.status()["execution_identity"] != execution_identity:
                raise Hold("execution identity was not bound by the arbiter")
            if checkpoint != self.arbiter.checkpoint_for(grant.request_id):
                raise Hold("resume checkpoint is not the arbiter's verified predecessor")
            self.command.verify_sources()
            self.arbiter.require_workload(grant, self.command.fingerprint(), kind="cpu-owned-process")
            directory = self.state_directory / uuid.uuid4().hex
            directory.mkdir(mode=0o700)
            self._write(
                directory / "start.json",
                {
                    "schema": PROTOCOL,
                    "grant": asdict(grant),
                    "execution_identity": execution_identity,
                    "resume": json.loads(checkpoint.payload_json) if checkpoint else None,
                },
            )
            environment = {**dict(self.command.environment), "OCEAN_RESOURCE_RUN_DIR": str(directory)}
            job = None
            child = None
            fence = None
            gate_read = gate_write = None
            try:
                flags = 0
                argv = self.command.argv
                spawn_options = {}
                if os.name == "nt":
                    job = windows_job.create_kill_on_close_job()
                    flags = windows_job.CREATE_SUSPENDED | subprocess.CREATE_NO_WINDOW
                else:
                    gate_read, gate_write = os.pipe()
                    argv = (
                        str(Path(sys.executable).resolve()), "-I", "-S", "-c",
                        _POSIX_BOOTSTRAP, str(gate_read), *self.command.argv,
                    )
                    spawn_options["pass_fds"] = (gate_read,)
                child = subprocess.Popen(
                    argv,
                    cwd=self.command.cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    start_new_session=os.name != "nt",
                    **spawn_options,
                )
                if gate_read is not None:
                    os.close(gate_read)
                    gate_read = None
                if os.name == "nt":
                    try:
                        self.arbiter.require_workload(grant, self.command.fingerprint(), kind="cpu-owned-process")
                        windows_job.assign_and_resume(job, child)
                    except BaseException:
                        # Assignment can fail while the child is suspended and
                        # not in the empty job yet. Reap that explicit Popen;
                        # terminating the job alone would leave it suspended.
                        if _reap_unassigned_child(child) is not None:
                            raise Hold("suspended child bootstrap cleanup failed")
                        raise
                else:
                    fence = _capture_posix_process_fence(child.pid)
                run = _Execution(grant, execution_identity, directory, child, fence, job)
                self._executions[grant] = run
                if gate_write is not None:
                    self.arbiter.require_workload(grant, self.command.fingerprint(), kind="cpu-owned-process")
                    os.write(gate_write, b"G")
                    os.close(gate_write)
                    gate_write = None
                self._wait_message(run, "ready.json")
                self.arbiter.require_running(grant)
                return True
            except BaseException:
                cleaned = False
                try:
                    if child is not None:
                        if os.name != "nt" and fence is None:
                            # Only the isolated waiting bootstrap can exist here.
                            _terminate_unfenced_posix_child(child, self.timeout)
                            if child.poll() is None:
                                raise Hold("waiting bootstrap cleanup is unconfirmed")
                        else:
                            _terminate_child(child, self.timeout, process_fence=fence, job_handle=job)
                    cleaned = True
                finally:
                    if job is not None:
                        windows_job.close_job(job)
                        if grant in self._executions:
                            self._executions[grant].job = None
                    if cleaned:
                        self._executions.pop(grant, None)
                raise
            finally:
                for descriptor in (gate_read, gate_write):
                    if descriptor is not None:
                        os.close(descriptor)

    def checkpoint(self, grant: Grant, execution_identity: str) -> Checkpoint:
        self._require_process()
        with self._mutex:
            run = self._execution(grant, execution_identity)
            if run.exited:
                if (
                    run.accepted is None
                    or not run.accepted.valid_for(grant)
                    or self._message(run.directory / "accepted.checkpoint.json") != asdict(run.accepted)
                ):
                    raise Hold("persisted accepted checkpoint changed or is unavailable")
                return run.accepted
            self._write(
                run.directory / "checkpoint.request.json",
                {"schema": PROTOCOL, "grant": asdict(grant), "execution_identity": execution_identity},
            )
            value = self._wait_message(run, "checkpoint.json")
            payload = value.get("payload")
            if (
                value.get("quiescent") is not True
                or not isinstance(payload, dict)
                or self.validator(payload) is not True
            ):
                raise Hold("application checkpoint is not verified and quiescent")
            run.accepted = Checkpoint.create(grant, payload)
            self._write(run.directory / "accepted.checkpoint.json", asdict(run.accepted))
            return run.accepted

    def stop(self, grant: Grant, execution_identity: str, checkpoint: Checkpoint):
        self._require_process()
        with self._mutex:
            run = self._execution(grant, execution_identity)
            if run.accepted != checkpoint or not checkpoint.valid_for(grant):
                raise Hold("stop requires this execution's verified checkpoint")
            if self._message(run.directory / "accepted.checkpoint.json") != asdict(checkpoint):
                raise Hold("persisted accepted checkpoint changed or is unavailable")
            if run.exited:
                # A failed capacity readback must be retryable without signalling
                # a closed Windows job or a potentially reused POSIX group.
                return
            _terminate_child(run.child, self.timeout, process_fence=run.fence, job_handle=run.job)
            deadline = time.monotonic() + self.timeout
            while not self._empty(run):
                if time.monotonic() >= deadline:
                    raise Hold("owned process tree is not confirmed empty")
                time.sleep(0.02)
            run.exited = True
            if run.job is not None:
                windows_job.close_job(run.job)
                run.job = None

    @staticmethod
    def _empty(run: _Execution) -> bool:
        if run.child.poll() is None:
            return False
        if os.name == "nt":
            return run.job is not None and windows_job.active_process_count(run.job) == 0
        return run.fence is not None and _posix_group_empty(run.fence["pgid"])

    def readback(self, grant: Grant, execution_identity: str) -> ExitReadback:
        self._require_process()
        with self._mutex:
            run = self._execution(grant, execution_identity)
            exited = run.exited and run.child.poll() is not None
            return ExitReadback(grant, execution_identity, exited, 0 if exited else None, time.monotonic())

    def measure_usage(self, grant: Grant, execution_identity: str) -> dict:
        """Observe only a currently owned live tree; samples are not peak bounds.

        Short-lived/reparented children and external/GPU allocations can escape
        discrete sampling. Such workloads require separate evidence/review.
        No process is adopted, signalled or granted capacity by this method.
        """
        self._require_process()
        with self._mutex:
            run = self._execution(grant, execution_identity)
            if run.exited or run.child.poll() is not None:
                raise Hold("usage measurement requires this owned live execution")
            from .capacity import _psutil
            try:
                started = time.monotonic()
                backend = _psutil()
                process = backend.Process(run.child.pid)
                family = [process, *process.children(recursive=True)]
                if len(family) > 256:
                    raise ValueError("process observation exceeds bound")
                members = []
                for member in family:
                    with member.oneshot():
                        created = member.create_time()
                        rss = member.memory_info().rss
                        cpu = member.cpu_times()
                    seconds = cpu.user + cpu.system
                    if not instant(created) or not instant(seconds) or type(rss) is not int or rss < 0:
                        raise ValueError("process resource counters unavailable")
                    members.append({"pid": member.pid, "created_at": created, "rss_bytes": rss, "cpu_seconds": seconds})
                if run.child.poll() is not None or not instant(started):
                    raise ValueError("owned execution exited during resource observation")
                return {"schema": "ocean-owned-usage-sample.v1", "grant": asdict(grant),
                        "execution_identity": execution_identity, "observed_at": started,
                        "members": members, "rss_bytes": sum(m["rss_bytes"] for m in members),
                        "cpu_seconds": sum(m["cpu_seconds"] for m in members),
                        "scope": "sampled-live-process-tree-not-an-external-residency-proof"}
            except Exception as exc:
                raise Hold("owned process resource observation failed") from exc

    def close(self):
        """Own-process emergency cleanup; never releases the arbiter or claims a checkpoint."""
        if os.getpid() != self._pid:
            return  # A forked child must never signal the parent's owned work.
        with self._mutex:
            for run in self._executions.values():
                if not run.exited:
                    _terminate_child(run.child, self.timeout, process_fence=run.fence, job_handle=run.job)
                    if run.job is not None:
                        windows_job.close_job(run.job)
                        run.job = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
