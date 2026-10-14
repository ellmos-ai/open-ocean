"""Neutral contracts for the first offline hybrid resource seam."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


class Hold(RuntimeError):
    """No permission to start, release or mutate arbiter state."""


def identity(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("identity must be a non-empty bounded string")
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in value):
        raise ValueError("identity must be a portable token")
    if value in {".", ".."}:
        raise ValueError("identity must not be a relative path")
    return value


def positive(value: object) -> bool:
    return type(value) is int and value > 0


def instant(value: object) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def sha256_hex(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("exact lower-case SHA-256 required")
    return value


@dataclass(frozen=True)
class ResourceSocket:
    """A large consumer, not the agent/job that uses it."""
    socket_id: str
    host_id: str
    ram_bytes: int | None
    cpu_units: int | None
    profile_id: str | None = None
    workload_sha256: str | None = None

    def __post_init__(self):
        identity(self.socket_id)
        identity(self.host_id)
        if self.profile_id is not None:
            identity(self.profile_id)
        if self.workload_sha256 is not None:
            sha256_hex(self.workload_sha256)

    @property
    def profiled(self) -> bool:
        return positive(self.ram_bytes) and positive(self.cpu_units) and self.profile_id is not None


@dataclass(frozen=True)
class HybridPlannerPointer:
    """Reference only. This object never creates or edits a planner/compute job."""
    planner: str
    task_id: str
    executor: str
    job_id: str
    source_sha256: str

    def __post_init__(self):
        for value in (self.planner, self.task_id, self.executor, self.job_id):
            identity(value)
        if len(self.source_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.source_sha256):
            raise ValueError("pointer requires an exact lower-case SHA-256")


@dataclass(frozen=True)
class SlotRequest:
    """One user of a socket; both identities remain separate."""
    request_id: str
    socket_id: str
    slot_id: str
    host_id: str
    idempotency_key: str
    priority: int = 3
    interactive: bool = False
    pointer: HybridPlannerPointer | None = None

    def __post_init__(self):
        for value in (self.request_id, self.socket_id, self.slot_id, self.host_id, self.idempotency_key):
            identity(value)
        if type(self.priority) is not int or not 1 <= self.priority <= 4:
            raise ValueError("priority must be P1..P4")
        if type(self.interactive) is not bool:
            raise ValueError("interactive must be boolean")


@dataclass(frozen=True)
class CapacityReadback:
    host_id: str
    sequence: int
    observed_at: float
    available_ram_bytes: int | None
    available_cpu_units: int | None
    pressure_ok: bool | None
    reserve_verified: bool | None = None

    def usable(self, host: str, now: float, max_age: float, after: int = 0) -> bool:
        return (
            self.host_id == host and positive(self.sequence) and self.sequence > after
            and instant(self.observed_at) and instant(now)
            and 0 <= now - self.observed_at <= max_age
            and positive(self.available_ram_bytes) and positive(self.available_cpu_units)
            and self.pressure_ok is True and self.reserve_verified is True
        )


@dataclass(frozen=True)
class Grant:
    authority_id: str
    generation: int
    request_id: str
    socket_id: str
    slot_id: str


@dataclass(frozen=True)
class Checkpoint:
    grant: Grant
    payload_json: str
    payload_sha256: str

    @classmethod
    def create(cls, grant: Grant, payload: dict) -> Checkpoint:
        if not isinstance(payload, dict):
            raise ValueError("checkpoint payload must be a JSON object")
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(content.encode("utf-8")) > 1024 * 1024:
            raise ValueError("checkpoint exceeds 1 MiB")
        return cls(grant, content, hashlib.sha256(content.encode("utf-8")).hexdigest())

    def valid_for(self, grant: Grant) -> bool:
        try:
            payload = json.loads(self.payload_json)
            expected = Checkpoint.create(grant, payload)
        except (ValueError, TypeError):
            return False
        return self == expected


@dataclass(frozen=True)
class ExitReadback:
    grant: Grant
    execution_identity: str
    exited: bool | None
    resident_bytes: int | None
    observed_at: float


@dataclass(frozen=True)
class Override:
    request_id: str
    reason: str
    expires_at: float

    def __post_init__(self):
        identity(self.request_id)
        if not isinstance(self.reason, str) or not self.reason.strip() or len(self.reason) > 256:
            raise ValueError("override requires a bounded reason")
        if not instant(self.expires_at):
            raise ValueError("override expiry must be finite")
