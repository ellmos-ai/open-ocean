"""Single-writer, fail-closed admission state machine for an offline first seam.

No OS process, model, queue, timer service or BACH database is discovered here.
A capacity sensor and execution proofs are explicitly injected trusted ports.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import wraps
from threading import RLock
from copy import deepcopy
from typing import Callable

from .authority import HostWriterAuthority
from .contracts import (
    CapacityReadback, Checkpoint, ExitReadback, Grant, Hold, Override,
    ResourceSocket, SlotRequest, identity, instant, positive,
)


def serialized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
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


class HostLocalArbiter:
    """One torch (socket + slot), with no implicit release on TTL or failure."""
    def __init__(
        self, authority: HostWriterAuthority, sockets: tuple[ResourceSocket, ...],
        sensor: Callable[[], CapacityReadback], clock: Callable[[], float],
        *, fixture_profiles: frozenset[str] = frozenset(), max_age: float = 2,
        heartbeat_ttl: float = 10, max_chat_burst: int = 3,
        max_override_seconds: float = 60,
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
        authority.claim_arbiter()
        self._mutex = RLock()
        self.authority = authority
        self._sockets = {s.socket_id: s for s in sockets}
        self._profiles = fixture_profiles
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
        # Only named fixture profiles may use this first seam. Real adapters are
        # deliberately not admitted until a later profile/authorization review.
        if not socket.profiled or socket.profile_id not in self._profiles:
            raise Hold("unprofiled or unauthorized socket; real adapter admission remains closed")
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

    @serialized
    def bind_execution(self, grant: Grant, execution_identity: str):
        active = self._current(grant)
        identity(execution_identity)
        if active.execution_identity is not None and active.execution_identity != execution_identity:
            raise Hold("execution identity cannot change")
        active.execution_identity = execution_identity
        self.authority.record(asdict(active))

    @serialized
    def request_for(self, grant: Grant) -> SlotRequest:
        self._current(grant)
        return self._requests[grant.request_id]

    @serialized
    def require_running(self, grant: Grant):
        active = self._current(grant)
        if active.return_requested or self._now() > active.heartbeat_until:
            raise Hold("return requested or heartbeat expired")

    @serialized
    def heartbeat(self, grant: Grant):
        active = self._current(grant)
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
            "mode": "offline-first-seam-no-live-adapters",
            "host_id": self.authority.host_id,
            "generation": self._generation,
            "torch": asdict(active.grant) if active else None,
            "execution_identity": active.execution_identity if active else None,
            "return_requested": active.return_requested if active else False,
            "heartbeat_expired": self._now() > active.heartbeat_until if active else False,
            "waiting": [asdict(self._requests[r]) for r in self._pending],
            "override": asdict(self._override) if self._override else None,
            "events": deepcopy(self._events),
            "restart_recovery": "HOLD-until-independent-residency-reconciliation",
            "polarstern_lease": "separate-unchanged",
        }
