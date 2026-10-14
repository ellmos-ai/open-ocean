"""Native capacity port with explicit reserves; a reading is never a grant.

CPU headroom is measured from two per-CPU cumulative counter snapshots. Core
count and load average alone never establish available CPU. psutil is optional
and imported only by the explicit native observation path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
import math
import os
from pathlib import Path
import platform
from threading import RLock
import time

from .contracts import CapacityReadback, Hold, identity, instant, positive
from .host import sample_host


@dataclass(frozen=True)
class CapacityPolicy:
    reserve_ram_bytes: int
    reserve_cpu_units: int
    reserve_disk_bytes: int
    directory: Path
    sample_seconds: float = 0.25
    max_age_seconds: float = 2.0

    def __post_init__(self):
        if not all(positive(v) for v in (
            self.reserve_ram_bytes, self.reserve_cpu_units, self.reserve_disk_bytes,
        )):
            raise ValueError("explicit positive RAM, CPU and disk reserves required")
        if not instant(self.sample_seconds) or not 0.1 <= self.sample_seconds <= 1:
            raise ValueError("CPU sampling interval must be 0.1..1 seconds")
        if not instant(self.max_age_seconds) or not self.sample_seconds < self.max_age_seconds <= 5:
            raise ValueError("freshness must exceed sampling interval and be at most 5 seconds")
        p = self.directory
        if not isinstance(p, Path) or not p.is_absolute() or not p.is_dir() or p.resolve() != p.absolute():
            raise ValueError("explicit existing unlinked absolute filesystem directory required")


def idle_cpu_units(before: tuple[dict, ...], after: tuple[dict, ...], eligible: tuple[int, ...]) -> float:
    """Conservative observed idle shares, including I/O wait as busy.

Linux guest counters duplicate user/nice time and are excluded from totals.
Other optional counters count as busy; this can understate capacity (e.g.
overlapping Windows interrupt counters), but cannot turn them into idle time.
Every individual counter must be finite, nonnegative and nondecreasing.
"""
    if not isinstance(before, tuple) or not isinstance(after, tuple) or not before or len(before) != len(after):
        raise ValueError("CPU topology changed or is unknown")
    if (
        not isinstance(eligible, tuple) or not eligible or len(set(eligible)) != len(eligible)
        or any(type(i) is not int or not 0 <= i < len(before) for i in eligible)
    ):
        raise ValueError("unknown CPU affinity")
    fractions = []
    for old, new in zip(before, after):
        if (
            not isinstance(old, dict) or not isinstance(new, dict) or set(old) != set(new)
            or not {"user", "system", "idle"} <= set(old) or len(old) > 64
            or any(not isinstance(k, str) for k in old)
        ):
            raise ValueError("CPU counter schema changed")
        if any(not instant(old[k]) or not instant(new[k]) or new[k] < old[k] for k in old):
            raise ValueError("invalid or regressing CPU counters")
        delta = {k: new[k] - old[k] for k in old}
        total = sum(value for key, value in delta.items() if key not in {"guest", "guest_nice"})
        if not math.isfinite(total) or total <= 0 or not 0 <= delta["idle"] <= total:
            raise ValueError("CPU counters made no valid progress")
        fractions.append(delta["idle"] / total)
    return sum(fractions[i] for i in eligible)


def _psutil():
    try:
        import psutil
    except ImportError as exc:
        raise Hold("optional native resource dependency unavailable") from exc
    if not (5, 9, 6) <= psutil.version_info < (8,):
        raise Hold("unsupported native resource dependency version")
    return psutil


def _cpu_snapshot(backend) -> tuple[dict, ...]:
    return tuple(dict(row._asdict()) for row in backend.cpu_times(percpu=True))


def _eligible_cpus(backend, system: str, count: int) -> tuple[int, ...]:
    if system == "Darwin":
        return tuple(range(count))  # macOS exposes no psutil CPU-affinity API.
    if system == "Windows" and count > 64:
        raise Hold("Windows processor-group budget is unverified")
    result = tuple(sorted(backend.Process().cpu_affinity()))
    if not result or len(set(result)) != len(result) or any(type(i) is not int or not 0 <= i < count for i in result):
        raise Hold("CPU affinity is unavailable or inconsistent")
    return result


def _windows_in_job() -> bool:
    """Ask whether any Windows Job constrains this process, including parents.

    Querying only the innermost Job's limits cannot prove the effective budget.
    Unknown membership must not silently become unrestricted host capacity.
    """
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.argtypes = []
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    api.IsProcessInJob.restype = wintypes.BOOL
    inside = wintypes.BOOL()
    if not api.IsProcessInJob(api.GetCurrentProcess(), None, ctypes.byref(inside)):
        raise Hold("windows-job-membership-unavailable")
    return bool(inside.value)


class NativeCapacitySensor:
    """Process-bound trusted sensor port; default profile/claim gates stay separate.

    Windows Jobs and Linux cgroups remain closed until their effective RAM/CPU
    constraints are proved. No native queue/service/model is discovered.
    """

    def __init__(self, policy: CapacityPolicy, host_id: str | None = None):
        self.policy = policy
        self.host_id = identity(platform.node() if host_id is None else host_id)
        self._pid = os.getpid()
        self._sequence = 0
        self._mutex = RLock()
        self.last_observation: dict | None = None

    def observe(self) -> dict:
        # A child may inherit a mutex held by a vanished parent thread. Reject
        # the foreign PID before touching that mutex or any native backend.
        if os.getpid() != self._pid:
            raw = time.monotonic()
            reading = CapacityReadback(self.host_id, self._sequence + 1,
                                       raw if instant(raw) else 0.0, None, None, None, False)
            return self._report(reading, ["foreign-host-or-process"], None)
        with self._mutex:
            self._sequence += 1
            started_raw = time.monotonic()
            started = started_raw if instant(started_raw) else 0.0
            reading = CapacityReadback(self.host_id, self._sequence, started, None, None, None, False)
            errors = []
            observed_idle = None
            observations = []
            try:
                if not instant(started_raw):
                    raise Hold("native-clock-unavailable")
                if os.getpid() != self._pid or platform.node() != self.host_id:
                    raise Hold("foreign-host-or-process")
                backend = _psutil()
                first = sample_host(self.policy.directory)
                observations.append(first)
                if first.host_id != self.host_id or first.platform not in {"Windows", "Darwin", "Linux"}:
                    raise Hold("unsupported-or-foreign-host")
                if first.platform == "Windows" and _windows_in_job():
                    raise Hold("effective-windows-job-budget-unverified")
                before = _cpu_snapshot(backend)
                eligible = _eligible_cpus(backend, first.platform, len(before))
                cpu_started = time.monotonic()
                time.sleep(self.policy.sample_seconds)
                after = _cpu_snapshot(backend)
                cpu_finished = time.monotonic()
                if not instant(cpu_started) or not instant(cpu_finished):
                    raise Hold("native-clock-unavailable")
                if cpu_finished - cpu_started < self.policy.sample_seconds * 0.9:
                    raise Hold("CPU-sampling-window-too-short")
                if _eligible_cpus(backend, first.platform, len(after)) != eligible:
                    raise Hold("CPU-affinity-changed")
                observed_idle = idle_cpu_units(before, after, eligible)
                last = sample_host(self.policy.directory)
                observations.append(last)
                if first.platform == "Windows" and _windows_in_job():
                    raise Hold("effective-windows-job-budget-unverified")
                if (
                    last.host_id != self.host_id or last.platform != first.platform
                    or first.total_ram_bytes != last.total_ram_bytes
                    or first.logical_cpus != len(before) or last.logical_cpus != len(after)
                ):
                    raise Hold("host-topology-changed")
                if any(o.available_ram_bytes is None or o.disk_free_bytes is None for o in observations):
                    raise Hold("memory-or-disk-unavailable")
                ram = max(0, min(o.available_ram_bytes for o in observations) - self.policy.reserve_ram_bytes)
                cpu = max(0, math.floor(observed_idle - self.policy.reserve_cpu_units))
                pressure = all(o.pressure == "normal" for o in observations)
                disk = min(o.disk_free_bytes for o in observations) >= self.policy.reserve_disk_bytes
                # The first snapshot is the oldest input. Never refresh its age
                # simply because a later probe or output serialization completed.
                fresh = 0 <= time.monotonic() - started <= self.policy.max_age_seconds
                if not fresh:
                    errors.append("stale-observation-window")
                if first.platform == "Linux":
                    errors.append("effective-cgroup-budget-unverified")
                if not pressure:
                    errors.append("memory-pressure-not-normal")
                if not disk:
                    errors.append("disk-reserve-unavailable")
                if not ram or not cpu:
                    errors.append("insufficient-observed-headroom")
                reading = CapacityReadback(self.host_id, self._sequence, started, ram, cpu, pressure,
                                           fresh and disk and first.platform != "Linux")
            except Exception as exc:
                # No private paths, process command lines or backend exceptions.
                errors.append(str(exc) if isinstance(exc, Hold) else "native-capacity-probe-failed")
            return self._report(reading, errors, observed_idle)

    def _report(self, reading, errors, observed_idle):
        result = {
            "schema": "ocean-native-capacity.v1", "mode": "read-only-capacity-observation",
            "start_authorized": False, "reading": asdict(reading),
            "observed_idle_cpu_units": observed_idle, "errors": errors,
            "state": "CANDIDATE" if not errors else "HOLD",
            "system_reserve": {"ram_bytes": self.policy.reserve_ram_bytes,
                               "cpu_units": self.policy.reserve_cpu_units,
                               "disk_bytes": self.policy.reserve_disk_bytes},
            "profile_admission": "separate-default-closed", "models_started": 0, "queue_writes": 0,
        }
        self.last_observation = deepcopy(result)
        return result

    def __call__(self) -> CapacityReadback:
        return CapacityReadback(**self.observe()["reading"])
