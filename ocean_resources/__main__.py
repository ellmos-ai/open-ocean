"""JSON-only, offline CLI. Default manifest is read-only; fixture-demo owns temp state."""
from __future__ import annotations

import argparse
from importlib.resources import files
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from . import (
    BACHFacade, CapacityReadback, Checkpoint, ComputeExecutorAdapter, ExitReadback,
    HostLocalArbiter, HostWriterAuthority, ResourceSocket, SlotRequest,
)


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
    parser = argparse.ArgumentParser(description="Ocean resource seam: offline manifest or explicit fixture demonstration")
    parser.add_argument("command", nargs="?", choices=("manifest", "fixture-demo"), default="manifest")
    args = parser.parse_args(argv)
    report = manifest() if args.command == "manifest" else fixture_demo()
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
