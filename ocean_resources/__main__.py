"""JSON-only, offline CLI. Default manifest is read-only; fixture-demo owns temp state."""
from __future__ import annotations

import argparse
from importlib.resources import files
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from . import (
    BACHFacade, CapacityReadback, Checkpoint, ComputeExecutorAdapter, ExitReadback,
    HostLocalArbiter, HostWriterAuthority, ResourceSocket, SlotRequest,
)
from .host import sample_host
from .pipelines import ResourceBudget, catalog_document, load_catalog, shadow_plan


def manifest() -> dict:
    return json.loads(files("ocean_resources").joinpath("manifest.json").read_text(encoding="utf-8"))


def fixture_demo() -> dict:
    # All budgets/metrics and executors are synthetic. No OS job, model or live
    # queue is touched. The only writes are the own temporary writer journal.
    now = 100.0
    sequence = 0
    progress, starts = {}, []
    running = set()

    def sensor():
        nonlocal sequence
        sequence += 1
        return CapacityReadback("fixture-host", sequence, now, 128, 2, True, True)

    def start(grant, request, checkpoint, eid):
        progress[grant.request_id] = json.loads(checkpoint.payload_json)["progress"] if checkpoint else 0
        starts.append({"request_id": grant.request_id, "resumed_progress": progress[grant.request_id]})
        running.add(eid)
        return True

    def checkpoint(grant, eid):
        return Checkpoint.create(grant, {"progress": progress[grant.request_id]})

    def stop(grant, eid, cp):
        running.remove(eid)

    def readback(grant, eid):
        return ExitReadback(grant, eid, eid not in running, 0 if eid not in running else None, now)

    with TemporaryDirectory(prefix="ocean-resource-fixture-") as directory:
        with HostWriterAuthority(Path(directory).resolve(), "fixture-host") as writer:
            sockets = tuple(ResourceSocket(s, "fixture-host", 64, 1, "fixture") for s in ("compute", "model"))
            arbiter = HostLocalArbiter(writer, sockets, sensor, lambda: now, fixture_profiles=frozenset({"fixture"}))
            adapter = ComputeExecutorAdapter(start, checkpoint, stop, readback)
            facade = BACHFacade(arbiter, {"compute": adapter, "model": adapter})
            arbiter.submit(SlotRequest("compute-job", "compute", "compute-slot", "fixture-host", "compute-key"))
            first = facade.start_next()
            progress["compute-job"] = 7
            arbiter.submit(SlotRequest("chat", "model", "telegram-slot", "fixture-host", "chat-key", 1, True))
            facade.yield_active(first)
            chat = facade.start_next()
            facade.yield_active(chat, requeue=False)
            resumed = facade.start_next()
            progress["compute-job"] = 14
            facade.yield_active(resumed, requeue=False)
            report = arbiter.status()
    return {
        "mode": "synthetic-fixture-only", "models_started": 0, "live_queue_writes": 0,
        "host_ram_measurement": "not-performed-synthetic-capacity",
        "starts": starts, "result_progress": 14, "final": report,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ocean resource coordination: manifest, explicit fixture or read-only host/pipeline observation")
    parser.add_argument("command", nargs="?", choices=("manifest", "fixture-demo", "host", "catalog", "shadow", "capacity"), default="manifest")
    parser.add_argument("--jobs", type=Path, help="Explicit job projection JSON; no queue discovery")
    parser.add_argument("--catalog", type=Path, help="Optional explicit reference-only catalogue JSON")
    parser.add_argument("--reserve-ram-bytes", type=int)
    parser.add_argument("--reserve-disk-bytes", type=int)
    parser.add_argument("--reserve-cpu-units", type=int)
    parser.add_argument("--capacity-directory", type=Path)
    parser.add_argument("--sample-seconds", type=float)
    args = parser.parse_args(argv)
    try:
        if args.command == "capacity":
            if args.jobs is not None or args.catalog is not None:
                parser.error("capacity does not read job projections or catalogues")
            from .capacity import CapacityPolicy, NativeCapacitySensor
            policy = CapacityPolicy(args.reserve_ram_bytes, args.reserve_cpu_units, args.reserve_disk_bytes,
                                    args.capacity_directory, args.sample_seconds if args.sample_seconds is not None else 0.25)
            report = NativeCapacitySensor(policy).observe()
        elif any(value is not None for value in (args.reserve_cpu_units, args.capacity_directory, args.sample_seconds)):
            parser.error("CPU sampling options belong to capacity only")
        elif args.command == "shadow":
            if args.jobs is None:
                parser.error("shadow requires --jobs and explicit RAM/disk reserves")
            budget = ResourceBudget(args.reserve_ram_bytes, args.reserve_disk_bytes)
            # Bound file reads; reject non-JSON, NaN and duplicate JSON keys.
            def read_json(path):
                def unique(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("duplicate JSON key")
                        result[key] = value
                    return result
                with path.open("rb") as stream:
                    payload = stream.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024:
                    raise ValueError("projection too large")
                return json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                                  parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
            jobs = read_json(args.jobs)
            catalog = load_catalog(read_json(args.catalog)) if args.catalog else load_catalog()
            observation = sample_host()
            report = shadow_plan(jobs, observation, budget, now=time.time(), catalog=catalog)
        elif any(value is not None for value in (args.jobs, args.catalog, args.reserve_ram_bytes, args.reserve_disk_bytes)):
            parser.error("projection and reserve options belong to shadow only")
        elif args.command == "host":
            report = sample_host().to_dict()
        elif args.command == "catalog":
            report = catalog_document()
        else:
            report = manifest() if args.command == "manifest" else fixture_demo()
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"state": "HOLD", "start_authorized": False, "error": type(exc).__name__,
                          "reason": "invalid or unavailable explicit observation input"}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
