"""Native CPU deltas and explicit reserves; no workload/profile is authorized."""
from dataclasses import replace
import json
import os
import platform
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ocean_resources.capacity import CapacityPolicy, NativeCapacitySensor, idle_cpu_units
from ocean_resources.host import HostObservation
import ocean_resources.capacity as capacity


def counters(idle=100.0, user=10.0, system=10.0):
    return {"user": user, "system": system, "idle": idle}


def test_cpu_is_measured_from_deltas_and_restricted_affinity():
    before = tuple(counters() for _ in range(4))
    after = tuple(counters(idle=101, user=10 if i < 2 else 19) for i in range(4))
    assert idle_cpu_units(before, after, (0, 1, 2, 3)) == pytest.approx(2.2)
    assert idle_cpu_units(before, after, (2, 3)) == pytest.approx(0.2)


def test_duplicated_guest_time_does_not_reduce_real_idle_share():
    old = ({**counters(), "guest": 1.0},)
    new = ({**counters(idle=101, user=11), "guest": 2.0},)
    assert idle_cpu_units(old, new, (0,)) == 0.5


@pytest.mark.parametrize("before,after,eligible", [
    ((), (), (0,)),
    ((counters(),), (), (0,)),
    ((counters(),), (counters(),), (0,)),
    ((counters(),), (counters(idle=99),), (0,)),
    ((counters(),), (counters(idle=float("nan")),), (0,)),
    ((counters(),), (counters(user=True, idle=101),), (0,)),
    ((counters(),), (counters(idle=101),), (True,)),
    ((counters(),), (counters(idle=101),), (0, 0)),
    ((counters(),), (counters(idle=101),), (1,)),
    ((counters(),), ({"idle": 101, "user": 10},), (0,)),
])
def test_unknown_or_regressing_cpu_counters_never_establish_capacity(before, after, eligible):
    with pytest.raises(ValueError):
        idle_cpu_units(before, after, eligible)


@pytest.mark.parametrize("field,value", [
    ("reserve_ram_bytes", 0), ("reserve_cpu_units", True), ("reserve_disk_bytes", -1),
    ("sample_seconds", 0), ("sample_seconds", float("nan")), ("sample_seconds", 2),
    ("max_age_seconds", 0.1), ("max_age_seconds", float("inf")),
])
def test_reserves_and_sampling_are_explicit_bounded_policy(tmp_path, field, value):
    policy = CapacityPolicy(100, 1, 200, tmp_path.resolve())
    with pytest.raises(ValueError):
        replace(policy, **{field: value})


@pytest.fixture
def native_fake(tmp_path, monkeypatch):
    clock = [100.0]
    host = HostObservation("native-host", "Windows", 1000, 10000, 9000, 4, None, "normal", 5000, "fixture")
    hosts = [host, replace(host, available_ram_bytes=8000, disk_free_bytes=4000)]
    data = {"clock": clock, "hosts": hosts, "affinity": (0, 1, 2, 3), "samples": 0}

    def snapshot(*args, **kwargs):
        data["samples"] += 1
        # Four CPU shares idle; a mere CPU count does not set this value.
        return tuple(SimpleNamespace(_asdict=lambda: counters(idle=100 + clock[0])) for _ in range(4))

    backend = SimpleNamespace(
        version_info=(7, 2, 2), cpu_times=snapshot,
        Process=lambda: SimpleNamespace(cpu_affinity=lambda: data["affinity"]),
    )
    monkeypatch.setattr(capacity, "_psutil", lambda: backend)
    monkeypatch.setattr(capacity.platform, "node", lambda: "native-host")
    monkeypatch.setattr(capacity.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(capacity.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(capacity, "sample_host", lambda directory: hosts.pop(0))
    data["sensor"] = NativeCapacitySensor(CapacityPolicy(1000, 1, 2000, tmp_path.resolve()))
    return data


def test_native_port_subtracts_all_reserves_and_uses_oldest_measurement(native_fake):
    report = native_fake["sensor"].observe()
    assert report["state"] == "CANDIDATE" and report["errors"] == []
    reading = report["reading"]
    assert reading["available_ram_bytes"] == 7000
    assert reading["available_cpu_units"] == 3
    assert reading["observed_at"] == 100
    assert reading["reserve_verified"] is True
    assert native_fake["samples"] == 2 and report["start_authorized"] is False
    report["reading"]["reserve_verified"] = False
    assert native_fake["sensor"].last_observation["reading"]["reserve_verified"] is True


@pytest.mark.parametrize("change,reason", [
    ({"pressure": "critical"}, "memory-pressure-not-normal"),
    ({"disk_free_bytes": 1999}, "disk-reserve-unavailable"),
    ({"available_ram_bytes": None}, "memory-or-disk-unavailable"),
    ({"available_ram_bytes": 999}, "insufficient-observed-headroom"),
    ({"total_ram_bytes": 11000}, "host-topology-changed"),
    ({"host_id": "foreign"}, "host-topology-changed"),
])
def test_unknown_pressure_topology_or_headroom_stays_hold(native_fake, change, reason):
    native_fake["hosts"][1] = replace(native_fake["hosts"][1], **change)
    report = native_fake["sensor"].observe()
    assert report["state"] == "HOLD" and reason in report["errors"]
    assert not native_fake["sensor"].last_observation["start_authorized"]


def test_no_cpu_headroom_cannot_be_invented_from_core_count(native_fake):
    native_fake["affinity"] = (0,)
    report = native_fake["sensor"].observe()
    assert report["reading"]["available_cpu_units"] == 0
    assert report["state"] == "HOLD"


def test_linux_effective_cgroup_budget_is_never_inferred_from_host_totals(native_fake):
    native_fake["hosts"][:] = [replace(o, platform="Linux") for o in native_fake["hosts"]]
    report = native_fake["sensor"].observe()
    assert report["reading"]["reserve_verified"] is False
    assert "effective-cgroup-budget-unverified" in report["errors"]


def test_oldest_input_is_not_freshened_by_slow_followup_probe(native_fake, monkeypatch):
    original = capacity.sample_host
    def slow(directory):
        host = original(directory)
        native_fake["clock"][0] += 2
        return host
    monkeypatch.setattr(capacity, "sample_host", slow)
    report = native_fake["sensor"].observe()
    assert report["reading"]["observed_at"] == 100
    assert report["reading"]["reserve_verified"] is False
    assert "stale-observation-window" in report["errors"]


def test_missing_native_dependency_or_foreign_process_produces_unknown(native_fake, monkeypatch):
    monkeypatch.setattr(capacity, "_psutil", lambda: (_ for _ in ()).throw(ImportError("private/path")))
    result = native_fake["sensor"]()
    assert result.available_ram_bytes is None and result.available_cpu_units is None
    assert result.reserve_verified is False
    assert "private/path" not in json.dumps(native_fake["sensor"].last_observation)
    first = result.sequence
    monkeypatch.setattr(capacity.os, "getpid", lambda: -1)
    second = native_fake["sensor"]()
    assert second.sequence > first and second.reserve_verified is False


def test_unknown_native_clock_is_hold_without_nonfinite_json(native_fake, monkeypatch):
    monkeypatch.setattr(capacity.time, "monotonic", lambda: float("nan"))
    report = native_fake["sensor"].observe()
    assert report["state"] == "HOLD" and "native-clock-unavailable" in report["errors"]
    assert report["reading"]["reserve_verified"] is False
    json.dumps(report, allow_nan=False)


def test_actual_native_observation_is_read_only_and_never_a_grant(tmp_path):
    pytest.importorskip("psutil")
    result = NativeCapacitySensor(CapacityPolicy(1024 * 1024, 1, 1024 * 1024, tmp_path.resolve())).observe()
    assert result["start_authorized"] is False
    assert result["models_started"] == 0 and result["queue_writes"] == 0
    assert result["reading"]["host_id"] == platform.node()
    assert list(tmp_path.iterdir()) == []
    if sys.platform.startswith("linux"):
        assert result["reading"]["reserve_verified"] is False


def test_capacity_cli_requires_explicit_reserves_and_does_not_start_anything(tmp_path):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    missing = subprocess.run([sys.executable, "-m", "ocean_resources", "capacity"], env=env,
                             capture_output=True, text=True, timeout=15)
    assert missing.returncode == 2 and json.loads(missing.stdout)["state"] == "HOLD"
    report = subprocess.run([
        sys.executable, "-m", "ocean_resources", "capacity", "--reserve-ram-bytes", "1048576",
        "--reserve-cpu-units", "1", "--reserve-disk-bytes", "1048576",
        "--capacity-directory", str(tmp_path.resolve()),
    ], env=env, capture_output=True, text=True, timeout=20)
    assert report.returncode == 0, report.stderr
    payload = json.loads(report.stdout)
    assert payload["start_authorized"] is False and payload["models_started"] == 0
    assert list(tmp_path.iterdir()) == []


def test_native_measurement_cannot_enable_an_unapproved_workload_profile(native_fake, tmp_path):
    from ocean_resources import HostLocalArbiter, HostWriterAuthority, Hold, ResourceSocket, SlotRequest
    with HostWriterAuthority(tmp_path.resolve(), "native-host") as writer:
        arbiter = HostLocalArbiter(
            writer, (ResourceSocket("compute", "native-host", 100, 1, "unapproved-profile"),),
            native_fake["sensor"], capacity.time.monotonic,
        )
        arbiter.submit(SlotRequest("job", "compute", "slot", "native-host", "key"))
        with pytest.raises(Hold, match="unauthorized"):
            arbiter.acquire()
        assert native_fake["samples"] == 0
