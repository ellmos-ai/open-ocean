"""Cross-pipeline references, missing gates and resource headroom fail closed."""

from dataclasses import replace
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ocean_resources import BACHFacade, HostObservation, ResourceBudget, load_catalog, route_job, shadow_plan, slot_request
from ocean_resources.pipelines import catalog_document


def job(pipeline_id="1", **changes):
    definition = load_catalog()[pipeline_id]
    return {
        "job_id": "job-1",
        "pipeline_id": pipeline_id,
        "host_id": "test-host",
        "priority": 3,
        "interactive": False,
        "size_class": "large",
        "ram_bytes": 100,
        "cpu_units": 1,
        "disk_bytes": 100,
        "gates": {gate: True for gate in definition.gates},
        "planner": "bach",
        "task_id": "2190",
        "executor_job_id": "original-job",
        "source_sha256": "a" * 64,
        **changes,
    }


def host(**changes):
    return replace(
        HostObservation("test-host", "Windows", 100, 2000, 1000, 4, None, "normal", 2000, "test-probe"), **changes
    )


def plan(jobs, reading=None, now=101):
    return shadow_plan(jobs, reading or host(), ResourceBudget(100, 100), now=now)


def test_catalog_covers_all_original_groups_without_inventing_extra_pipelines():
    catalog = load_catalog()
    assert set(catalog) == {"1", *["2" + letter for letter in "abcdefghijk"], "3a", "3b", "4"}
    assert catalog["4"].targets == ("windows", "android", "ios")
    assert {entry.family for entry in catalog.values()} == {"research", "services", "media", "builds"}


@pytest.mark.parametrize("pipeline_id", list(load_catalog()))
def test_each_pipeline_reuses_original_executor_pointer_without_copying_job(pipeline_id):
    original = job(pipeline_id)
    before = copy.deepcopy(original)
    request = slot_request(original, load_catalog(), socket_id="worker", slot_id="job-slot")
    assert request.pointer.task_id == "2190"
    assert request.pointer.job_id == "original-job"
    assert request.pointer.executor == load_catalog()[pipeline_id].executor
    assert request.pointer.source_sha256 == "a" * 64
    assert original == before


def test_shadow_never_grants_authority_even_when_capacity_and_reported_gates_fit():
    result = plan([job()])
    assert result["jobs"][0]["state"] == "candidate-for-arbiter"
    assert result["start_authorized"] is False
    assert result["jobs"][0]["start_authorized"] is False
    assert result["torch"].startswith("unknown")
    assert result["models_started"] == result["queue_writes"] == 0


def test_bach_pipeline_port_accepts_build_work_without_model_schema_migration():
    original = job("4")
    request = BACHFacade.request_from_pipeline(original, load_catalog(), socket_id="build", slot_id="windows-build")
    assert request.pointer.executor == "software-build"
    assert request.slot_id == "windows-build"
    assert "required_model" not in original


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"gates": {}}, "gate:claim"),
        ({"ram_bytes": None}, "resource-profile-unknown"),
        ({"cpu_units": None}, "resource-profile-unknown"),
        ({"size_class": "unknown"}, "resource-profile-unknown"),
        ({"ram_bytes": 901}, "insufficient-ram-headroom"),
        ({"disk_bytes": 1901}, "insufficient-disk-headroom"),
        ({"host_id": "other-host"}, "requires-another-host"),
    ],
)
def test_job_cannot_bypass_unknown_profile_gate_or_reserved_capacity(changes, reason):
    entry = plan([job(**changes)])["jobs"][0]
    assert entry["state"] == "HOLD"
    assert reason in entry["reasons"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"observed_at": 0}, "stale-host-observation"),
        ({"observed_at": 102}, "stale-host-observation"),
        ({"pressure": "unknown"}, "host-pressure-or-probe-unknown"),
        ({"pressure": "critical"}, "host-pressure-or-probe-unknown"),
        ({"available_ram_bytes": None}, "insufficient-ram-headroom"),
        ({"disk_free_bytes": None}, "insufficient-disk-headroom"),
    ],
)
def test_unknown_or_stale_host_is_hold(changes, reason):
    entry = plan([job()], host(**changes))["jobs"][0]
    assert entry["state"] == "HOLD"
    assert reason in entry["reasons"]


def test_host_capability_precedes_central_preference():
    entry = plan([job("2h")], host(platform="Darwin"))["jobs"][0]
    assert "incompatible-platform" in entry["reasons"]


def test_small_work_still_needs_capacity_gates_and_budget():
    ready = plan([job(size_class="small")])["jobs"][0]
    assert ready["state"] == "candidate-for-small-work-check"
    assert ready["start_authorized"] is False
    assert plan([job(size_class="small", gates={})])["jobs"][0]["state"] == "HOLD"


def test_interactive_and_priority_order_is_observation_only_and_input_unchanged():
    jobs = [
        job(job_id="background", priority=1),
        job(job_id="chat", priority=3, interactive=True),
        job(job_id="maintenance", priority=4),
    ]
    before = copy.deepcopy(jobs)
    assert [row["job_id"] for row in plan(jobs)["jobs"]] == ["chat", "background", "maintenance"]
    assert jobs == before


@pytest.mark.parametrize(
    "changes",
    [
        {"priority": True},
        {"cpu_units": True},
        {"ram_bytes": -1},
        {"gates": {"claim": "yes"}},
        {"source_sha256": "A" * 64},
    ],
)
def test_invalid_projection_is_rejected(changes):
    with pytest.raises((ValueError, TypeError)):
        plan([job(**changes)])


def test_duplicate_jobs_and_unknown_pipeline_rejected():
    with pytest.raises(ValueError):
        plan([job(), job()])
    with pytest.raises(ValueError):
        plan([{**job(), "pipeline_id": "not-registered"}])


def test_catalog_cannot_declare_itself_an_execution_authority():
    document = catalog_document()
    document["mode"] = "execute"
    with pytest.raises(ValueError):
        load_catalog(document)
    document = catalog_document()
    document["pipelines"].append(document["pipelines"][0])
    with pytest.raises(ValueError):
        load_catalog(document)


def test_shadow_cli_fails_closed_on_duplicate_json_keys_and_missing_reserve(tmp_path):
    jobs = tmp_path / "jobs.json"
    jobs.write_text('[{"job_id":"x","job_id":"y"}]', encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ocean_resources",
            "shadow",
            "--jobs",
            str(jobs),
            "--reserve-ram-bytes",
            "1",
            "--reserve-disk-bytes",
            "1",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["state"] == "HOLD"
    assert jobs.read_text(encoding="utf-8") == '[{"job_id":"x","job_id":"y"}]'


@pytest.mark.parametrize("pipeline_id", ["1", "2k", "3a", "3b", "4"])
def test_heavy_compute_translation_media_and_builds_prefer_capable_central_host(pipeline_id):
    original = job(pipeline_id)
    before = copy.deepcopy(original)
    routed = route_job(
        original,
        (host(), host(host_id="central", platform="Darwin")),
        ResourceBudget(100, 100),
        central_host_id="central",
        local_host_id="test-host",
        recurring=False,
        now=101,
    )
    assert routed["proposed_host"] == "central"
    assert routed["start_authorized"] is False
    assert original == before


def test_windows_only_submission_falls_back_from_mac_to_capable_local_host():
    routed = route_job(
        job("2h"),
        (host(), host(host_id="central", platform="Darwin")),
        ResourceBudget(100, 100),
        central_host_id="central",
        local_host_id="test-host",
        recurring=True,
        now=101,
    )
    assert routed["proposed_host"] == "test-host"
    assert routed["fallback"] is True


def test_low_resource_one_off_prefers_local_but_recurring_service_prefers_central():
    for recurring, expected in [(False, "test-host"), (True, "central")]:
        routed = route_job(
            job("2a", size_class="small"),
            (host(), host(host_id="central")),
            ResourceBudget(100, 100),
            central_host_id="central",
            local_host_id="test-host",
            recurring=recurring,
            now=101,
        )
        assert routed["proposed_host"] == expected


def test_no_unknown_host_or_pressure_can_be_routed_as_ready():
    routed = route_job(
        job(),
        (host(pressure="critical"),),
        ResourceBudget(100, 100),
        central_host_id="central",
        local_host_id="test-host",
        recurring=True,
        now=101,
    )
    assert routed["proposed_host"] is None
