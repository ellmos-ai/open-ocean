"""Generic pipeline catalogue and shadow planning, never a second execution queue."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from typing import Any

from .contracts import HybridPlannerPointer, SlotRequest, identity, instant, positive
from .host import HostObservation


@dataclass(frozen=True)
class PipelineDefinition:
    pipeline_id: str
    name: str
    family: str
    executor: str
    platforms: tuple[str, ...]
    gates: tuple[str, ...]
    targets: tuple[str, ...] = ()

    def __post_init__(self):
        for token in (self.pipeline_id, self.family, self.executor, *self.gates, *self.targets):
            identity(token)
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 160:
            raise ValueError("pipeline name must be bounded")
        if not self.platforms or any(p not in {"Windows", "Darwin", "Linux"} for p in self.platforms):
            raise ValueError("explicit supported platforms required")
        if len(set(self.gates)) != len(self.gates) or not self.gates:
            raise ValueError("unique nonempty pipeline gates required")


def load_catalog(document: Any = None) -> dict[str, PipelineDefinition]:
    if document is None:
        document = json.loads(files("ocean_resources").joinpath("pipeline-catalog.json").read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"schema", "mode", "pipelines"}:
        raise ValueError("invalid catalogue envelope")
    if document["schema"] != "ocean-pipeline-catalog.v1" or document["mode"] != "reference-only":
        raise ValueError("catalogue never authorizes execution")
    rows = document["pipelines"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("bounded pipeline list required")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "pipeline_id",
            "name",
            "family",
            "executor",
            "platforms",
            "gates",
            "targets",
        }:
            raise ValueError("invalid pipeline fields")
        for key in ("platforms", "gates", "targets"):
            if not isinstance(row[key], list) or any(not isinstance(t, str) for t in row[key]):
                raise ValueError("pipeline lists require strings")
        entry = PipelineDefinition(
            **{
                **row,
                "platforms": tuple(row["platforms"]),
                "gates": tuple(row["gates"]),
                "targets": tuple(row["targets"]),
            }
        )
        if entry.pipeline_id in result:
            raise ValueError("duplicate pipeline identity")
        result[entry.pipeline_id] = entry
    return result


def catalog_document() -> dict:
    document = json.loads(files("ocean_resources").joinpath("pipeline-catalog.json").read_text(encoding="utf-8"))
    load_catalog(document)
    return document


@dataclass(frozen=True)
class ResourceBudget:
    """Explicit headroom, not a certified model RAM profile or a CPU measurement."""

    reserve_ram_bytes: int
    reserve_disk_bytes: int
    max_observation_age: float = 5.0

    def __post_init__(self):
        if not positive(self.reserve_ram_bytes) or not positive(self.reserve_disk_bytes):
            raise ValueError("explicit positive RAM and disk headroom required")
        if not instant(self.max_observation_age) or self.max_observation_age <= 0:
            raise ValueError("positive finite observation age required")


def validate_job(job: Any, catalog: dict[str, PipelineDefinition]) -> dict:
    fields = {
        "job_id",
        "pipeline_id",
        "host_id",
        "priority",
        "interactive",
        "size_class",
        "ram_bytes",
        "cpu_units",
        "disk_bytes",
        "gates",
        "planner",
        "task_id",
        "executor_job_id",
        "source_sha256",
    }
    if not isinstance(job, dict) or set(job) != fields:
        raise ValueError("explicit exact pipeline job fields required")
    for key in ("job_id", "pipeline_id", "host_id", "executor_job_id"):
        identity(job[key])
    if job["pipeline_id"] not in catalog:
        raise ValueError("unknown pipeline")
    if type(job["priority"]) is not int or job["priority"] not in range(1, 5):
        raise ValueError("priority must be P1..P4")
    if type(job["interactive"]) is not bool or job["size_class"] not in {"small", "large", "unknown"}:
        raise ValueError("explicit interaction and resource class required")
    for key in ("ram_bytes", "cpu_units", "disk_bytes"):
        if job[key] is not None and not positive(job[key]):
            raise ValueError("resource demand must be positive or unknown")
    if not isinstance(job["gates"], dict) or any(
        not isinstance(k, str) or type(v) is not bool for k, v in job["gates"].items()
    ):
        raise ValueError("gate states must be explicit booleans")
    entry = catalog[job["pipeline_id"]]
    HybridPlannerPointer(job["planner"], job["task_id"], entry.executor, job["executor_job_id"], job["source_sha256"])
    return dict(job)


def slot_request(job: dict, catalog: dict[str, PipelineDefinition], *, socket_id: str, slot_id: str) -> SlotRequest:
    """Pure adapter for ANY pipeline, not just model-backed BACH tasks."""
    job = validate_job(job, catalog)
    if job["size_class"] != "large":
        raise ValueError("only explicit large work requests a resource socket")
    entry = catalog[job["pipeline_id"]]
    pointer = HybridPlannerPointer(
        job["planner"], job["task_id"], entry.executor, job["executor_job_id"], job["source_sha256"]
    )
    return SlotRequest(
        job["job_id"], socket_id, slot_id, job["host_id"], job["job_id"], job["priority"], job["interactive"], pointer
    )


def shadow_plan(
    jobs: list[dict],
    observation: HostObservation,
    budget: ResourceBudget,
    *,
    now: float,
    catalog: dict[str, PipelineDefinition] | None = None,
) -> dict:
    """Observe and explain. Even an eligible candidate receives no permission."""
    catalog = load_catalog() if catalog is None else catalog
    if not isinstance(jobs, list) or len(jobs) > 10000:
        raise ValueError("bounded explicit job projection required")
    checked = [validate_job(job, catalog) for job in jobs]
    if len({job["job_id"] for job in checked}) != len(checked):
        raise ValueError("duplicate job identity")
    candidates = []
    fresh = (
        instant(now)
        and instant(observation.observed_at)
        and 0 <= now - observation.observed_at <= budget.max_observation_age
    )
    for job in sorted(checked, key=lambda x: (not x["interactive"], x["priority"])):
        entry = catalog[job["pipeline_id"]]
        reasons = []
        if not fresh:
            reasons.append("stale-host-observation")
        if job["host_id"] != observation.host_id:
            reasons.append("requires-another-host")
        if observation.platform not in entry.platforms:
            reasons.append("incompatible-platform")
        if observation.pressure != "normal" or observation.errors:
            reasons.append("host-pressure-or-probe-unknown")
        if job["size_class"] == "unknown" or any(job[k] is None for k in ("ram_bytes", "cpu_units", "disk_bytes")):
            reasons.append("resource-profile-unknown")
        for gate in entry.gates:
            if job["gates"].get(gate) is not True:
                reasons.append("gate:" + gate)
        if (
            observation.available_ram_bytes is None
            or job["ram_bytes"] is None
            or (observation.available_ram_bytes - budget.reserve_ram_bytes < job["ram_bytes"])
        ):
            reasons.append("insufficient-ram-headroom")
        if (
            observation.disk_free_bytes is None
            or job["disk_bytes"] is None
            or (observation.disk_free_bytes - budget.reserve_disk_bytes < job["disk_bytes"])
        ):
            reasons.append("insufficient-disk-headroom")
        # Logical cores and load averages are NOT an authoritative free-CPU probe.
        # The actual arbiter/adaptor must provide its separately accepted CPU profile.
        state = (
            "HOLD"
            if reasons
            else ("candidate-for-arbiter" if job["size_class"] == "large" else "candidate-for-small-work-check")
        )
        candidates.append(
            {
                "job_id": job["job_id"],
                "pipeline_id": entry.pipeline_id,
                "executor": entry.executor,
                "executor_job_id": job["executor_job_id"],
                "state": state,
                "reasons": reasons,
                "start_authorized": False,
            }
        )
    return {
        "schema": "ocean-pipeline-shadow.v1",
        "mode": "read-only-shadow",
        "host": observation.to_dict(),
        "jobs": candidates,
        "queue_writes": 0,
        "models_started": 0,
        "start_authorized": False,
        "torch": "unknown-until-connected-to-native-arbiter",
        "requires_before_execution": [
            "authoritative-cpu-profile",
            "native-claim-and-budget",
            "profiled-executor",
            "current-resource-grant",
            "source-and-native-gate-readback",
        ],
    }


def route_job(
    job: dict,
    observations: tuple[HostObservation, ...],
    budget: ResourceBudget,
    *,
    central_host_id: str,
    local_host_id: str,
    recurring: bool,
    now: float,
    catalog: dict[str, PipelineDefinition] | None = None,
) -> dict:
    """Propose central heavy/recurring work; platform and headroom checks win.

    This changes neither the original host-bound request nor its executor.
    """
    identity(central_host_id)
    identity(local_host_id)
    if type(recurring) is not bool:
        raise ValueError("recurrence must be explicit")
    catalog = load_catalog() if catalog is None else catalog
    validate_job(job, catalog)
    if len({host.host_id for host in observations}) != len(observations):
        raise ValueError("duplicate host observations")
    preferred = central_host_id if recurring or job["size_class"] == "large" else local_host_id
    order = list(dict.fromkeys([preferred, local_host_id, central_host_id]))
    by_host = {host.host_id: host for host in observations}
    candidates = []
    selected = None
    for host_id in order:
        if host_id not in by_host:
            candidates.append({"host_id": host_id, "state": "HOLD", "reasons": ["host-observation-missing"]})
            continue
        proposed = {**job, "host_id": host_id}
        result = shadow_plan([proposed], by_host[host_id], budget, now=now, catalog=catalog)["jobs"][0]
        candidates.append({"host_id": host_id, **result})
        if selected is None and result["state"] != "HOLD":
            selected = host_id
    return {
        "mode": "routing-proposal-only",
        "preferred_host": preferred,
        "proposed_host": selected,
        "fallback": selected is not None and selected != preferred,
        "candidates": candidates,
        "start_authorized": False,
        "queue_writes": 0,
    }
