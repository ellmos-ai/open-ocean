"""Explicitly pinned reviewed workload envelopes, separate from live capacity.

The configured file pins are the approval boundary, not a JSON boolean. Sampled
resource observations are evidence for a reviewed allocation, not a kernel limit
or a proof of worst-case RSS/CPU. This first native scope is CPU-owned processes;
model/GPU/external-daemon residency needs a different independently proved scope.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time

from .contracts import Hold, ResourceSocket, identity, instant, positive, sha256_hex


def _local_file(path):
    if (not isinstance(path, Path) or not path.is_absolute() or path.drive.startswith("\\\\")
        or any(p.lower().startswith("onedrive") for p in path.parts)
        or not path.is_file() or path.is_symlink() or path.resolve() != path.absolute()):
        raise ValueError("explicit existing unlinked host-local profile/evidence file required")


def _document(path: Path, expected_sha: str, limit: int) -> dict:
    _local_file(path)
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit or hashlib.sha256(content).hexdigest() != expected_sha:
        raise ValueError("profile/evidence bytes changed or exceed bounds")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate profile/evidence JSON key")
            result[key] = value
        return result

    def finite(value):
        raise ValueError("nonfinite profile/evidence JSON")

    result = json.loads(content.decode("utf-8"), object_pairs_hook=unique, parse_constant=finite)
    if not isinstance(result, dict):
        raise ValueError("profile/evidence object required")
    return result


@dataclass(frozen=True)
class ProfileSource:
    profile_path: Path
    profile_sha256: str
    evidence_path: Path

    def __post_init__(self):
        _local_file(self.profile_path)
        _local_file(self.evidence_path)
        sha256_hex(self.profile_sha256)


class ReviewedProfileGate:
    """Trusted operator-configured allowlist; never writes/approves a profile.

    Profiles and evidence are re-read on every check. Native queue/claim/budget
    and publication permissions remain outside this gate. Configuration cannot
    be supplied by an untrusted work request. No fixture names are enabled here.
    """
    def __init__(self, sources: tuple[ProfileSource, ...], *, max_age_seconds: float, wall_clock=time.time):
        if (not isinstance(sources, tuple) or not sources or len(sources) > 256
            or any(not isinstance(s, ProfileSource) for s in sources)):
            raise ValueError("explicit bounded immutable profile sources required")
        if not instant(max_age_seconds) or max_age_seconds <= 0 or not callable(wall_clock):
            raise ValueError("explicit positive profile age and wall clock required")
        self._pid, self._host = os.getpid(), identity(platform.node())
        self._platform, self._architecture = platform.system(), platform.machine()
        self._max_age, self._clock = max_age_seconds, wall_clock
        self._sources = {}
        for source in sources:
            profile = self._load(source)
            key = profile["profile_id"]
            if key in self._sources:
                raise ValueError("duplicate approved profile identity")
            self._sources[key] = source

    def _load(self, source):
        profile = _document(source.profile_path, source.profile_sha256, 64 * 1024)
        if set(profile) != {"schema", "kind", "profile_id", "socket_id", "host_id", "platform", "architecture",
                            "workload_sha256", "ram_bytes", "cpu_units", "ram_margin_bytes", "evidence_sha256",
                            "approved_by", "approved_at", "expires_at"}:
            raise ValueError("exact reviewed workload profile fields required")
        if profile["schema"] != "ocean-reviewed-workload-profile.v1" or profile["kind"] != "cpu-owned-process":
            raise ValueError("unsupported workload profile scope")
        for key in ("profile_id", "socket_id", "host_id", "approved_by"):
            identity(profile[key])
        for key in ("workload_sha256", "evidence_sha256"):
            sha256_hex(profile[key])
        if any(not positive(profile[k]) for k in ("ram_bytes", "cpu_units", "ram_margin_bytes")):
            raise ValueError("positive explicit reviewed allocations required")
        if (profile["host_id"] != self._host or profile["platform"] != self._platform
            or profile["architecture"] != self._architecture):
            raise ValueError("reviewed profile belongs to a different native host")
        evidence = _document(source.evidence_path, profile["evidence_sha256"], 4 * 1024 * 1024)
        if set(evidence) != {"schema", "scope", "method", "host_id", "platform", "architecture", "workload_sha256",
                             "peak_rss_bytes", "peak_cpu_units", "cpu_concurrency_units", "sample_count",
                             "sample_interval_seconds", "started_at", "finished_at", "exit_verified",
                             "checkpoint_verified", "unmeasured_external_residency"}:
            raise ValueError("exact native measurement fields required")
        if (evidence["schema"] != "ocean-workload-measurement.v1" or evidence["scope"] != "cpu-process-tree"
            or evidence["method"] != "sampled-rss-and-cumulative-cpu-v1"
            or evidence["exit_verified"] is not True or evidence["checkpoint_verified"] is not True
            or evidence["unmeasured_external_residency"] is not False):
            raise ValueError("unsupported or incomplete measurement scope")
        if any(evidence[k] != profile[k] for k in ("host_id", "platform", "architecture", "workload_sha256")):
            raise ValueError("measurement and profile workload identities differ")
        if (not positive(evidence["peak_rss_bytes"]) or not positive(evidence["sample_count"])
            or not 2 <= evidence["sample_count"] <= 10_000_000 or not positive(evidence["cpu_concurrency_units"])
            or not instant(evidence["peak_cpu_units"])
            or not instant(evidence["sample_interval_seconds"]) or evidence["sample_interval_seconds"] <= 0):
            raise ValueError("bounded native observations and reviewed CPU concurrency required")
        if (profile["ram_bytes"] < evidence["peak_rss_bytes"] + profile["ram_margin_bytes"]
            or profile["cpu_units"] < evidence["cpu_concurrency_units"]
            or math.ceil(evidence["peak_cpu_units"]) > evidence["cpu_concurrency_units"]):
            raise ValueError("reviewed allocation does not cover observations and explicit margins")
        duration = evidence["finished_at"] - evidence["started_at"] if all(
            instant(evidence[k]) for k in ("finished_at", "started_at")) else -1
        interval = (evidence["sample_count"] - 1) * evidence["sample_interval_seconds"]
        if not instant(duration) or not instant(interval) or duration < interval * 0.9:
            raise ValueError("measurement interval and sample count exceed the recorded window")
        now = self._clock()
        times = (evidence["started_at"], evidence["finished_at"], profile["approved_at"], profile["expires_at"], now)
        if (not all(instant(t) for t in times)
            or not evidence["started_at"] < evidence["finished_at"] <= profile["approved_at"] <= now < profile["expires_at"]
            or now - evidence["finished_at"] > self._max_age):
            raise ValueError("measurement/profile UTC window is stale, future or invalid")
        return profile

    def require(self, socket: ResourceSocket) -> dict:
        try:
            if (os.getpid() != self._pid or platform.node() != self._host
                or platform.system() != self._platform or platform.machine() != self._architecture):
                raise ValueError("foreign profile authority process/host")
            source = self._sources.get(socket.profile_id)
            if source is None:
                raise ValueError("profile is not in the configured allowlist")
            profile = self._load(source)
            if any(profile[k] != getattr(socket, k) for k in
                   ("profile_id", "socket_id", "host_id", "workload_sha256", "ram_bytes", "cpu_units")):
                raise ValueError("socket does not match the reviewed workload envelope")
            return profile
        except Exception as exc:
            raise Hold("reviewed workload profile is unavailable, changed, expired or mismatched") from exc

    def inspect(self) -> dict:
        """Read-only validation for configured pins; never acquires a grant."""
        try:
            if (os.getpid() != self._pid or platform.node() != self._host
                or platform.system() != self._platform or platform.machine() != self._architecture):
                raise ValueError("foreign profile inspection process/host")
            profiles = [self._load(source) for source in self._sources.values()]
            return {"schema": "ocean-reviewed-profile-inspection.v1", "state": "VALIDATED",
                    "mode": "read-only-profile-validation", "start_authorized": False,
                    "profiles": profiles, "models_started": 0, "queue_writes": 0}
        except Exception as exc:
            raise Hold("reviewed profile inspection failed") from exc
