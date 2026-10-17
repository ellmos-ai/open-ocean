"""Single-writer, fail-closed admission state machine for an offline first seam.

No OS process, model, queue, timer service or BACH database is discovered here.
A capacity sensor and execution proofs are explicitly injected trusted ports.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import wraps
import json
import os
from pathlib import Path
from threading import RLock
from copy import deepcopy
from typing import Callable

from .authority import HostWriterAuthority
from .profiles import ReviewedProfileGate
from .contracts import (
    CapacityReadback, Checkpoint, ExitReadback, Grant, Hold, Override,
    ResourceSocket, SlotRequest, identity, instant, positive, sha256_hex,
)


def serialized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        if os.getpid() != self._pid:
            raise Hold("foreign arbiter process")
        with self._mutex:
            return method(self, *args, **kwargs)
    return guarded


@dataclass
class _Active:
    grant: Grant
    metric_sequence: int
    started_at: float
    heartbeat_until: float
    execution_identity: str | None = None
    return_requested: bool = False
    execution_evidence: dict | None = None
    checkpoint_evidence: dict | None = None


class HostLocalArbiter:
    """One torch (socket + slot), with no implicit release on TTL or failure."""
    def __init__(
        self, authority: HostWriterAuthority, sockets: tuple[ResourceSocket, ...],
        sensor: Callable[[], CapacityReadback], clock: Callable[[], float],
        *, fixture_profiles: frozenset[str] = frozenset(), max_age: float = 2,
        heartbeat_ttl: float = 10, max_chat_burst: int = 3,
        max_override_seconds: float = 60,
        profile_gate: ReviewedProfileGate | None = None,
    ):
        authority.require()
        if authority.unresolved() is not None:
            raise Hold("unresolved previous torch; independent restart reconciliation required")
        for value in (max_age, heartbeat_ttl, max_override_seconds):
            if not instant(value) or value <= 0:
                raise ValueError("policy durations must be positive and finite")
        if not positive(max_chat_burst):
            raise ValueError("chat burst must be a positive integer")
        if len({s.socket_id for s in sockets}) != len(sockets):
            raise ValueError("duplicate socket identity")
        if any(s.host_id != authority.host_id for s in sockets):
            raise ValueError("all sockets must belong to the writer's host")
        if profile_gate is not None and not isinstance(profile_gate, ReviewedProfileGate):
            raise ValueError("explicit reviewed profile gate required")
        authority.claim_arbiter()
        self._pid = os.getpid()
        self._mutex = RLock()
        self.authority = authority
        self._sockets = {s.socket_id: s for s in sockets}
        self._profiles = fixture_profiles
        self._profile_gate = profile_gate
        self._sensor, self._clock = sensor, clock
        self._max_age, self._ttl = max_age, heartbeat_ttl
        self._burst, self._max_override = max_chat_burst, max_override_seconds
        self._requests: dict[str, SlotRequest] = {}
        self._keys: dict[str, SlotRequest] = {}
        self._pending: list[str] = []
        self._active: _Active | None = None
        self._checkpoints: dict[str, Checkpoint] = {}
        self._generation = 0
        self._last_metric = 0
        self._chat_run = 0
        self._override: Override | None = None
        self._controller_bound = False
        self._events: list[dict] = []
        self._authority_id = authority.authority_id

    def _require(self):
        self.authority.require()
        if self.authority.authority_id != self._authority_id:
            raise Hold("writer session changed; this arbiter is fenced")

    def _now(self) -> float:
        now = self._clock()
        if not instant(now):
            raise Hold("unknown monotonic clock")
        return now

    @serialized
    def claim_controller(self):
        """One cooperating controller, with no adoption of an existing torch."""
        self._require()
        if self._controller_bound or self._active is not None:
            raise Hold("controller already bound or active torch requires its original owner")
        self._controller_bound = True

    @serialized
    def now(self) -> float:
        self._require()
        return self._now()

    @serialized
    def next_request(self) -> SlotRequest:
        """Observe existing selection policy without acquiring or starting work."""
        self._require()
        return self._requests[self._select()]

    def _measure(self, after: int = 0) -> CapacityReadback:
        try:
            reading = self._sensor()
        except Exception as exc:
            raise Hold("capacity sensor failed") from exc
        if not isinstance(reading, CapacityReadback) or not reading.usable(
            self.authority.host_id, self._now(), self._max_age,
            after=max(after, self._last_metric),
        ):
            raise Hold("unknown, stale, repeated or foreign capacity readback")
        self._last_metric = reading.sequence
        return reading

    @serialized
    def submit(self, request: SlotRequest) -> str:
        self._require()
        old = self._keys.get(request.idempotency_key)
        if old is not None:
            if old != request:
                raise Hold("idempotency key conflicts with the original request")
            return old.request_id
        if request.host_id != self.authority.host_id or request.socket_id not in self._sockets:
            raise Hold("unknown socket or foreign host")
        if request.request_id in self._requests:
            raise Hold("request identity conflicts with the original request")
        self._requests[request.request_id] = request
        self._keys[request.idempotency_key] = request
        self._pending.append(request.request_id)
        self._events.append({"event": "submitted", "request_id": request.request_id})
        return request.request_id

    @serialized
    def set_override(self, override: Override | None):
        self._require()
        if override is not None:
            duration = override.expires_at - self._now()
            if override.request_id not in self._pending or not 0 < duration <= self._max_override:
                raise Hold("override must name a waiting request and have a bounded future expiry")
        self._override = override
        self._events.append({"event": "override", "value": asdict(override) if override else None})

    def _select(self) -> str:
        if not self._pending:
            raise Hold("no waiting slot")
        if self._override is not None:
            if self._override.expires_at <= self._now():
                self._override = None
            elif self._override.request_id in self._pending:
                return self._override.request_id
        chat = [r for r in self._pending if self._requests[r].interactive]
        background = [r for r in self._pending if not self._requests[r].interactive]
        candidates = chat if chat and (not background or self._chat_run < self._burst) else background
        return min(candidates, key=lambda r: (self._requests[r].priority, self._pending.index(r)))

    @serialized
    def acquire(self) -> Grant:
        self._require()
        if self._active is not None:
            raise Hold("existing torch has not been verifiably released")
        request = self._requests[self._select()]
        socket = self._sockets[request.socket_id]
        self._admit_profile(socket)
        reading = self._measure()
        if reading.available_ram_bytes < socket.ram_bytes or reading.available_cpu_units < socket.cpu_units:
            raise Hold("insufficient measured capacity after the system reserve")
        self._generation += 1
        grant = Grant(self._authority_id, self._generation, request.request_id, request.socket_id, request.slot_id)
        self._active = _Active(grant, reading.sequence, self._now(), self._now() + self._ttl)
        self.authority.record(asdict(self._active))
        self._pending.remove(request.request_id)
        self._chat_run = self._chat_run + 1 if request.interactive else 0
        if self._override and self._override.request_id == request.request_id:
            self._override = None
        self._events.append({"event": "granted", "grant": asdict(grant)})
        return grant

    def _current(self, grant: Grant) -> _Active:
        self._require()
        if self._active is None or self._active.grant != grant:
            raise Hold("stale, foreign or inactive grant")
        return self._active

    def _admit_profile(self, socket):
        if not socket.profiled:
            raise Hold("unprofiled or unauthorized socket; real adapter admission remains closed")
        if socket.profile_id in self._profiles:
            return None
        if self._profile_gate is None:
            raise Hold("unprofiled or unauthorized socket; real adapter admission remains closed")
        return self._profile_gate.require(socket)

    @serialized
    def require_workload(self, grant: Grant, workload_sha256: str | None, *, kind: str | None):
        self._current(grant)
        socket = self._sockets[grant.socket_id]
        profile = self._admit_profile(socket)
        if profile is not None and (profile["kind"] != kind or socket.workload_sha256 != workload_sha256):
            raise Hold("execution does not match the reviewed workload and kind")
        if socket.workload_sha256 is not None and socket.workload_sha256 != workload_sha256:
            raise Hold("execution command differs from the configured socket")

    @serialized
    def prepare_execution(self, grant: Grant, workload_sha256: str, *, source_mode: str):
        """Revalidate immediately before application activation; never free a torch."""
        self.require_running(grant)
        self.require_workload(grant, workload_sha256, kind="cpu-owned-process")
        socket = self._sockets[grant.socket_id]
        if socket.profile_id in self._profiles:
            return
        if source_mode != "frozen-python":
            raise Hold("reviewed execution requires a frozen supported application artifact")
        active = self._current(grant)
        reading = self._measure(after=active.metric_sequence)
        if reading.available_ram_bytes < socket.ram_bytes or reading.available_cpu_units < socket.cpu_units:
            raise Hold("insufficient fresh capacity at application activation")
        active.metric_sequence = reading.sequence
        self.authority.record(asdict(active))
        # Native measurements and durable writes can block. Approval and TTL
        # must still be valid after them, before any application instructions.
        self.require_workload(grant, workload_sha256, kind="cpu-owned-process")
        self.require_running(grant)
        if not 0 <= self._now() - reading.observed_at <= self._max_age:
            raise Hold("activation capacity expired during final approval checks")

    @serialized
    def bind_execution(self, grant: Grant, execution_identity: str):
        active = self._current(grant)
        identity(execution_identity)
        if active.execution_identity is not None and active.execution_identity != execution_identity:
            raise Hold("execution identity cannot change")
        active.execution_identity = execution_identity
        self.authority.record(asdict(active))

    @serialized
    def record_execution_evidence(self, grant: Grant, evidence: dict):
        """Persist process containment facts before the application gate may open.

        Evidence improves restart diagnosis. It is not an independent residency
        proof and never permits a new writer to adopt or release this execution.
        """
        active = self._current(grant)
        required = {
            "schema", "grant", "execution_identity", "command_sha256", "run_directory",
            "owner_pid", "process", "containment", "gate_state", "recorded_at",
        }
        if not isinstance(evidence, dict) or set(evidence) != required:
            raise Hold("invalid durable process evidence fields")
        try:
            if (evidence["schema"] != "ocean-process-evidence.v1"
                    or evidence["grant"] != asdict(grant)
                    or evidence["execution_identity"] != active.execution_identity
                    or not active.execution_identity):
                raise ValueError("execution binding")
            sha256_hex(evidence["command_sha256"])
            run_directory = evidence["run_directory"]
            if (not isinstance(run_directory, str) or not Path(run_directory).is_absolute()
                    or Path(run_directory).is_symlink()):
                raise ValueError("run directory")
            if not positive(evidence["owner_pid"]):
                raise ValueError("owner process")
            process = evidence["process"]
            if not isinstance(process, dict) or set(process) != {"pid", "created_at", "boot_time"}:
                raise ValueError("native process identity")
            if not positive(process["pid"]):
                raise ValueError("native process PID")
            for key in ("created_at", "boot_time"):
                if process[key] is not None and not instant(process[key]):
                    raise ValueError("native process time")
            containment = evidence["containment"]
            if not isinstance(containment, dict):
                raise ValueError("containment")
            if containment.get("kind") == "windows-kill-on-close-job":
                if set(containment) != {"kind", "assigned"} or containment["assigned"] is not True:
                    raise ValueError("Windows containment")
            elif containment.get("kind") == "posix-session-group":
                if (set(containment) != {"kind", "pgid", "sid"}
                        or containment["pgid"] != process["pid"]
                        or containment["sid"] != process["pid"]):
                    raise ValueError("POSIX containment")
            else:
                raise ValueError("unknown containment")
            if evidence["gate_state"] not in {"closed", "may-open"}:
                raise ValueError("application gate state")
            if not instant(evidence["recorded_at"]):
                raise ValueError("recorded time")
            json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise Hold("durable process evidence is invalid") from exc

        previous = active.execution_evidence
        if previous is None:
            if evidence["gate_state"] != "closed":
                raise Hold("process evidence must be durable while the application gate is closed")
        else:
            stable = required - {"gate_state", "recorded_at"}
            if any(previous.get(key) != evidence.get(key) for key in stable):
                raise Hold("durable process evidence identity changed")
            if previous["gate_state"] == evidence["gate_state"]:
                return
            if previous["gate_state"] != "closed" or evidence["gate_state"] != "may-open":
                raise Hold("durable process gate state cannot move backwards")
        active.execution_evidence = deepcopy(evidence)
        try:
            self.authority.record(asdict(active))
        except BaseException:
            active.execution_evidence = previous
            raise

    @serialized
    def record_checkpoint_evidence(self, grant: Grant, evidence: dict):
        """Bind a persisted accepted application checkpoint to the active journal."""
        active = self._current(grant)
        required = {
            "schema", "grant", "execution_identity", "command_sha256", "run_directory",
            "checkpoint_file", "checkpoint_file_sha256", "payload_sha256", "recorded_at",
        }
        if not isinstance(evidence, dict) or set(evidence) != required:
            raise Hold("invalid durable checkpoint evidence fields")
        try:
            execution = active.execution_evidence
            if (execution is None or execution["gate_state"] != "may-open"
                    or evidence["schema"] != "ocean-checkpoint-evidence.v1"
                    or evidence["grant"] != asdict(grant)
                    or evidence["execution_identity"] != active.execution_identity
                    or evidence["execution_identity"] != execution["execution_identity"]
                    or evidence["command_sha256"] != execution["command_sha256"]
                    or evidence["run_directory"] != execution["run_directory"]):
                raise ValueError("checkpoint binding")
            checkpoint_file = Path(evidence["checkpoint_file"])
            run_directory = Path(execution["run_directory"])
            if (not checkpoint_file.is_absolute() or checkpoint_file.is_symlink()
                    or checkpoint_file.parent != run_directory
                    or checkpoint_file.name != "accepted.checkpoint.json"):
                raise ValueError("checkpoint file")
            sha256_hex(evidence["checkpoint_file_sha256"])
            sha256_hex(evidence["payload_sha256"])
            if not instant(evidence["recorded_at"]):
                raise ValueError("checkpoint recorded time")
            json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise Hold("durable checkpoint evidence is invalid") from exc

        previous = active.checkpoint_evidence
        if previous is not None:
            stable = required - {"recorded_at"}
            if any(previous.get(key) != evidence.get(key) for key in stable):
                raise Hold("accepted checkpoint evidence cannot change within an execution")
            return deepcopy(previous)
        active.checkpoint_evidence = deepcopy(evidence)
        try:
            self.authority.record(asdict(active))
        except BaseException:
            active.checkpoint_evidence = previous
            raise
        return deepcopy(active.checkpoint_evidence)

    @serialized
    def require_checkpoint_evidence(self, grant: Grant, evidence: dict):
        """Require the accepted checkpoint binding to be present in the durable journal."""
        active = self._current(grant)
        if active.checkpoint_evidence != evidence:
            raise Hold("accepted checkpoint evidence is not recorded by the active arbiter")
        saved = self.authority.unresolved()
        if (not isinstance(saved, dict)
                or saved.get("grant") != asdict(grant)
                or saved.get("checkpoint_evidence") != evidence):
            raise Hold("accepted checkpoint evidence is not durably present in the writer journal")
        return deepcopy(evidence)

    @serialized
    def request_for(self, grant: Grant) -> SlotRequest:
        self._current(grant)
        return self._requests[grant.request_id]

    @serialized
    def require_running(self, grant: Grant):
        active = self._current(grant)
        self._admit_profile(self._sockets[grant.socket_id])
        if active.return_requested or self._now() > active.heartbeat_until:
            raise Hold("return requested or heartbeat expired")

    @serialized
    def heartbeat(self, grant: Grant):
        active = self._current(grant)
        self._admit_profile(self._sockets[grant.socket_id])
        now = self._now()
        if active.return_requested or now > active.heartbeat_until:
            raise Hold("return requested or heartbeat expired; exit verification still required")
        active.heartbeat_until = now + self._ttl

    @serialized
    def request_return(self, grant: Grant):
        active = self._current(grant)
        active.return_requested = True
        self._events.append({"event": "return-requested", "grant": asdict(grant)})

    @serialized
    def checkpoint_for(self, request_id: str) -> Checkpoint | None:
        return self._checkpoints.get(request_id)

    @serialized
    def release(self, grant: Grant, checkpoint: Checkpoint, exit_readback: ExitReadback, *, requeue: bool = True):
        active = self._current(grant)
        if type(requeue) is not bool:
            raise Hold("requeue must be boolean")
        if not isinstance(checkpoint, Checkpoint) or not checkpoint.valid_for(grant):
            raise Hold("checkpoint identity or integrity failed")
        now = self._now()
        if (
            not isinstance(exit_readback, ExitReadback) or exit_readback.grant != grant
            or active.execution_identity is None
            or exit_readback.execution_identity != active.execution_identity
            or exit_readback.exited is not True or type(exit_readback.resident_bytes) is not int
            or exit_readback.resident_bytes != 0 or not instant(exit_readback.observed_at)
            or exit_readback.observed_at < active.started_at
            or not 0 <= now - exit_readback.observed_at <= self._max_age
        ):
            raise Hold("exit and RAM release are not independently verified")
        reading = self._measure(after=active.metric_sequence)
        if reading.observed_at < exit_readback.observed_at:
            raise Hold("capacity readback precedes verified exit")
        self.authority.record(None)
        self._checkpoints[grant.request_id] = checkpoint
        self._active = None
        if requeue:
            self._pending.append(grant.request_id)
        self._events.append({"event": "released", "grant": asdict(grant), "requeued": requeue})

    @serialized
    def status(self) -> dict:
        self._require()
        active = self._active
        return {
            "schema": "ocean-resource-arbiter.v1",
            "mode": "reviewed-workload-profiles" if self._profile_gate else "offline-first-seam-no-live-adapters",
            "host_id": self.authority.host_id,
            "generation": self._generation,
            "torch": asdict(active.grant) if active else None,
            "execution_identity": active.execution_identity if active else None,
            "return_requested": active.return_requested if active else False,
            "heartbeat_expired": self._now() > active.heartbeat_until if active else False,
            "chat_burst_count": self._chat_run,
            "policy": {"max_chat_burst": self._burst, "heartbeat_ttl": self._ttl,
                       "max_override_seconds": self._max_override},
            "waiting": [asdict(self._requests[r]) for r in self._pending],
            "override": asdict(self._override) if self._override else None,
            "events": deepcopy(self._events),
            "restart_recovery": "HOLD-until-independent-residency-reconciliation",
            "polarstern_lease": "separate-unchanged",
        }
