"""Behavioural first-seam regressions; no live queue/service/model dependency."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from ocean_resources import (
    BACHFacade, CapacityReadback, Checkpoint, ComputeExecutorAdapter, ExitReadback,
    Hold, HostLocalArbiter, HostWriterAuthority, HybridPlannerPointer, ModelSocketBinding,
    ModelSocketInferenceAdapter, Override, ResourceSocket, SlotRequest,
)


class Harness:
    def __init__(self, tmp_path):
        self.now = 100.0
        self.sequence = 0
        self.capacity = {}
        self.authority = HostWriterAuthority(tmp_path, "fixture-host").__enter__()
        self.sockets = tuple(ResourceSocket(s, "fixture-host", 64, 1, "fixture-profile") for s in ("compute", "model"))
        self.arbiter = HostLocalArbiter(
            self.authority, self.sockets, self.measure, lambda: self.now,
            fixture_profiles=frozenset({"fixture-profile"}),
        )
        self.progress = {}
        self.executions = {}
        self.starts = []
        self.bad_exit = {}
        self.adapter = ComputeExecutorAdapter(self.start, self.checkpoint, self.stop, self.readback)
        self.facade = BACHFacade(self.arbiter, {"compute": self.adapter, "model": self.adapter})

    def close(self):
        self.authority.__exit__()

    def measure(self):
        self.sequence += 1
        fields = dict(host_id="fixture-host", sequence=self.sequence, observed_at=self.now,
                      available_ram_bytes=128, available_cpu_units=2, pressure_ok=True, reserve_verified=True)
        fields.update(self.capacity)
        return CapacityReadback(**fields)

    def request(self, name, *, socket="compute", interactive=False, priority=3):
        request = SlotRequest(name, socket, name + "-slot", "fixture-host", name + "-key", priority, interactive)
        self.arbiter.submit(request)
        return request

    def start(self, grant, request, checkpoint, execution_id):
        self.executions[execution_id] = True
        self.progress[request.request_id] = json.loads(checkpoint.payload_json)["progress"] if checkpoint else 0
        self.starts.append((request.request_id, self.progress[request.request_id]))
        return True

    def checkpoint(self, grant, execution_id):
        return Checkpoint.create(grant, {"progress": self.progress[grant.request_id]})

    def stop(self, grant, execution_id, checkpoint):
        self.executions[execution_id] = False

    def readback(self, grant, execution_id):
        fields = dict(grant=grant, execution_identity=execution_id, exited=not self.executions[execution_id],
                      resident_bytes=0, observed_at=self.now)
        fields.update(self.bad_exit)
        return ExitReadback(**fields)


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    try:
        yield harness
    finally:
        harness.close()


def test_compute_chat_checkpoint_exit_capacity_resume(h):
    original = h.request("compute-job")
    first = h.facade.start_next()
    h.progress["compute-job"] = 7
    h.request("telegram", socket="model", interactive=True, priority=1)
    checkpoint = h.facade.yield_active(first)
    assert checkpoint.valid_for(first)
    assert not any(h.executions.values())
    chat = h.facade.start_next()
    assert (chat.socket_id, chat.slot_id) == ("model", "telegram-slot")
    assert chat.generation == first.generation + 1
    h.facade.yield_active(chat, requeue=False)
    resumed = h.facade.start_next()
    assert h.starts[-1] == ("compute-job", 7)
    assert h.arbiter.request_for(resumed) == original
    h.progress["compute-job"] = 11
    final = h.facade.yield_active(resumed, requeue=False)
    assert json.loads(final.payload_json)["progress"] == 11
    assert h.arbiter.status()["torch"] is None
    assert h.authority.unresolved() is None


@pytest.mark.parametrize("field,value", [
    ("available_ram_bytes", None), ("available_ram_bytes", True),
    ("available_ram_bytes", 63), ("available_cpu_units", None),
    ("available_cpu_units", 0), ("pressure_ok", None), ("pressure_ok", False),
    ("pressure_ok", 1), ("observed_at", 90), ("observed_at", 101),
    ("observed_at", float("nan")), ("sequence", True), ("sequence", 0),
    ("host_id", "foreign-host"),
    ("reserve_verified", None), ("reserve_verified", False), ("reserve_verified", 1),
])
def test_unknown_stale_or_insufficient_metrics_hold_without_start(h, field, value):
    h.request("job")
    h.capacity[field] = value
    with pytest.raises(Hold):
        h.facade.start_next()
    assert h.starts == [] and h.arbiter.status()["torch"] is None


def test_unprofiled_or_unapproved_socket_never_authorizes(tmp_path):
    for socket in (
        ResourceSocket("x", "fixture-host", None, 1, "fixture"),
        ResourceSocket("x", "fixture-host", 64, 1, None),
        ResourceSocket("x", "fixture-host", 64, 1, "not-authorized"),
    ):
        with HostWriterAuthority(tmp_path, "fixture-host") as authority:
            arbiter = HostLocalArbiter(authority, (socket,), lambda: None, lambda: 1)
            arbiter.submit(SlotRequest("x", "x", "slot", "fixture-host", "key"))
            with pytest.raises(Hold, match="unprofiled or unauthorized"):
                arbiter.acquire()


def test_no_second_slot_can_run_until_release(h):
    h.request("a")
    first = h.facade.start_next()
    h.request("b")
    with pytest.raises(Hold, match="not been verifiably released"):
        h.facade.start_next()
    assert len(h.starts) == 1
    h.facade.yield_active(first, requeue=False)


@pytest.mark.parametrize("field,value", [
    ("exited", False), ("exited", None), ("exited", 1),
    ("resident_bytes", 1), ("resident_bytes", None), ("resident_bytes", False),
    ("execution_identity", "foreign-process"), ("observed_at", 90),
])
def test_bad_exit_never_releases_reservation(h, field, value):
    h.request("a")
    grant = h.facade.start_next()
    h.bad_exit[field] = value
    with pytest.raises(Hold):
        h.facade.yield_active(grant)
    assert h.arbiter.status()["torch"]["request_id"] == "a"
    assert h.authority.unresolved() is not None
    h.request("b")
    with pytest.raises(Hold):
        h.facade.start_next()


def test_release_requires_new_capacity_after_exit(h):
    h.request("a")
    grant = h.facade.start_next()
    h.capacity["sequence"] = h.sequence
    with pytest.raises(Hold, match="repeated"):
        h.facade.yield_active(grant)
    assert h.arbiter.status()["torch"] is not None


def test_checkpoint_corruption_does_not_stop(h):
    h.request("a")
    grant = h.facade.start_next()
    adapter = replace(h.adapter, checkpoint=lambda g, e: replace(h.checkpoint(g, e), payload_sha256="0" * 64))
    h.facade._executions[grant] = (adapter, h.facade._executions[grant][1])
    with pytest.raises(Hold, match="checkpoint invalid"):
        h.facade.yield_active(grant)
    assert any(h.executions.values())


def test_stale_generation_cannot_heartbeat_or_release(h):
    h.request("a")
    first = h.facade.start_next()
    cp = h.facade.yield_active(first)
    second = h.facade.start_next()
    assert second.generation > first.generation
    with pytest.raises(Hold, match="stale"):
        h.arbiter.heartbeat(first)
    with pytest.raises(Hold, match="stale"):
        h.arbiter.release(first, cp, ExitReadback(first, "x", True, 0, h.now))
    h.facade.yield_active(second, requeue=False)


def test_heartbeat_expiry_never_frees_ram(h):
    h.request("a")
    grant = h.facade.start_next()
    h.now += 11
    assert h.arbiter.status()["heartbeat_expired"]
    with pytest.raises(Hold):
        h.arbiter.heartbeat(grant)
    with pytest.raises(Hold):
        h.arbiter.acquire()
    h.facade.yield_active(grant, requeue=False)


def test_chat_burst_is_bounded_and_background_resumes(h):
    h.request("compute")
    for i in range(5):
        h.request("chat-" + str(i), socket="model", interactive=True, priority=1)
    order = []
    for _ in range(6):
        grant = h.facade.start_next()
        order.append(grant.request_id)
        h.facade.yield_active(grant, requeue=False)
    assert order == ["chat-0", "chat-1", "chat-2", "compute", "chat-3", "chat-4"]


def test_priority_and_user_override_are_distinct_and_bounded(h):
    h.request("low", priority=4)
    h.request("high", priority=1)
    h.arbiter.set_override(Override("low", "User selects this job", h.now + 10))
    grant = h.facade.start_next()
    assert grant.request_id == "low"
    h.facade.yield_active(grant, requeue=False)
    with pytest.raises(Hold):
        h.arbiter.set_override(Override("high", "Too long", h.now + 61))
    h.arbiter.set_override(Override("high", "User selects this job", h.now + 1))
    h.now += 2
    assert h.facade.start_next().request_id == "high"


def test_idempotent_submit_and_divergent_duplicate_hold(h):
    request = h.request("a")
    assert h.arbiter.submit(request) == "a"
    assert len(h.arbiter.status()["waiting"]) == 1
    with pytest.raises(Hold, match="idempotency"):
        h.arbiter.submit(replace(request, priority=1))
    with pytest.raises(Hold, match="request identity"):
        h.arbiter.submit(replace(request, idempotency_key="other"))


def test_foreign_host_and_unknown_socket_hold(h):
    request = SlotRequest("x", "compute", "s", "foreign", "k")
    with pytest.raises(Hold):
        h.arbiter.submit(request)
    with pytest.raises(Hold):
        h.arbiter.submit(replace(request, host_id="fixture-host", socket_id="missing"))


def test_adapter_exception_and_unverified_start_retain_torch(h):
    h.request("a")
    def fail(*args):
        raise RuntimeError("adapter failed")
    facade = BACHFacade(h.arbiter, {"compute": replace(h.adapter, start=fail)})
    with pytest.raises(Hold, match="start failed"):
        facade.start_next()
    assert h.arbiter.status()["execution_identity"]
    assert h.authority.unresolved()


def test_threaded_double_start_only_one_succeeds(h):
    h.request("a")
    h.request("b")
    def attempt():
        try:
            return h.facade.start_next()
        except Hold:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: attempt(), range(2)))
    assert len([g for g in result if g is not None]) == 1
    assert len(h.starts) == 1


def test_writer_exclusive_across_process_and_second_arbiter_hold(h, tmp_path):
    code = (
        "from pathlib import Path; from ocean_resources import HostWriterAuthority,Hold; "
        "a=HostWriterAuthority(Path(__import__('sys').argv[1]),'fixture-host'); "
        "\ntry: a.__enter__()\nexcept Hold: raise SystemExit(3)\nelse: a.__exit__(); raise SystemExit(0)"
    )
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 3, result.stderr
    with pytest.raises(Hold, match="already has an arbiter"):
        HostLocalArbiter(h.authority, (), lambda: None, lambda: 1)


def test_restart_fences_uncertain_torch_and_old_writer_session(tmp_path):
    h = Harness(tmp_path)
    h.request("a")
    grant = h.facade.start_next()
    h.close()
    with HostWriterAuthority(tmp_path, "fixture-host") as next_writer:
        assert next_writer.authority_id != grant.authority_id
        with pytest.raises(Hold, match="previous torch"):
            HostLocalArbiter(next_writer, (), lambda: None, lambda: 1)
    with pytest.raises(Hold):
        h.arbiter.heartbeat(grant)


@pytest.mark.parametrize("raw", [b"", b"0", b"0{}", b"0[]", b'0{"payload":3,"sha256":"x"}', b"0corrupt"])
def test_corrupt_restart_journal_holds(tmp_path, raw):
    (tmp_path / "fixture-host.writer").write_bytes(raw)
    with pytest.raises(Hold, match="journal"):
        HostWriterAuthority(tmp_path, "fixture-host").__enter__()


def test_writer_journal_rejects_records_over_the_restart_bound(tmp_path):
    with HostWriterAuthority(tmp_path, "fixture-host") as writer:
        with pytest.raises(Hold, match="size bound"):
            writer.record({"payload": "x" * (64 * 1024)})
        assert writer.unresolved() is None


def test_native_bach_gate_shape_and_task_fields_are_preserved(h):
    binding = ModelSocketBinding("model", "binding-1", "agent-1", "ollama", "model:fixture")
    pointer = HybridPlannerPointer("bach", "12", "compute", "job-12", hashlib.sha256(b"fixture").hexdigest())
    task = {"id": 12, "priority": "P3", "required_model": "model:fixture", "assigned_slot": "background-slot"}
    original = dict(task)
    request = BACHFacade.request_from_task(task, binding, pointer, host_id="fixture-host",
                                         request_id="bg", idempotency_key="bg-key")
    assert task == original and request.slot_id == "background-slot" and request.pointer == pointer
    assert request.socket_id == "model"
    bad = dict(task, required_model="other")
    with pytest.raises(Hold):
        BACHFacade.request_from_task(bad, binding, pointer, host_id="fixture-host", request_id="bg", idempotency_key="x")
    h.arbiter.submit(request)
    grant = h.facade.start_next()
    calls = []
    class Gate:
        @asynccontextmanager
        async def turn(self, chat_id, priority, *, check_ready, model_target):
            check_ready()
            calls.append((chat_id, priority, model_target))
            yield
    adapter = ModelSocketInferenceAdapter(h.arbiter, binding, Gate())
    async def invoke():
        async with adapter.turn(grant, "fixture-chat"):
            pass
    asyncio.run(invoke())
    assert calls == [("fixture-chat", "background", binding.target())]
    assert set(calls[0][2]) == {"socket_id", "binding_id", "agent_id", "backend", "model"}
    h.facade.yield_active(grant, requeue=False)


def test_actual_owned_dummy_child_checkpoint_exit_and_resume(h, tmp_path):
    # Real own process, 1 MiB allocation; it is never a model or production job.
    child = (
        "import json,sys; memory=bytearray(1024*1024); progress=int(sys.argv[1]); "
        "print('ready',flush=True); "
        "\nfor line in sys.stdin:\n"
        " if line.strip()=='checkpoint': progress+=7; print(json.dumps({'progress':progress}),flush=True)\n"
        " elif line.strip()=='exit': break\n"
    )
    processes = {}
    checkpoint_path = tmp_path / "owned-compute-checkpoint.json"
    def start(grant, request, checkpoint, eid):
        progress = json.loads(checkpoint.payload_json)["progress"] if checkpoint else 0
        process = subprocess.Popen([sys.executable, "-u", "-c", child, str(progress)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        processes[eid] = process
        assert process.stdout.readline().strip() == "ready"
        h.progress[request.request_id] = progress
        h.starts.append((request.request_id, progress))
        return process.poll() is None
    def checkpoint(grant, eid):
        process = processes[eid]
        process.stdin.write("checkpoint\n")
        process.stdin.flush()
        payload = json.loads(process.stdout.readline())
        cp = Checkpoint.create(grant, payload)
        checkpoint_path.write_text(cp.payload_json, encoding="utf-8")
        assert json.loads(checkpoint_path.read_text(encoding="utf-8")) == payload
        return cp
    def stop(grant, eid, cp):
        process = processes[eid]
        process.stdin.write("exit\n")
        process.stdin.flush()
        process.wait(timeout=5)
    def readback(grant, eid):
        process = processes[eid]
        exited = process.poll() == 0
        # A reaped own process has no resident allocation. This is NOT a claim
        # that host-wide allocatable memory grew by exactly one MiB.
        return ExitReadback(grant, eid, exited, 0 if exited else None, h.now)
    real_adapter = ComputeExecutorAdapter(start, checkpoint, stop, readback)
    facade = BACHFacade(h.arbiter, {"compute": real_adapter, "model": h.adapter})
    try:
        h.request("owned-compute")
        first = facade.start_next()
        h.request("chat", socket="model", interactive=True)
        facade.yield_active(first)
        assert all(p.poll() == 0 for p in processes.values())
        chat = facade.start_next()
        facade.yield_active(chat, requeue=False)
        resumed = facade.start_next()
        assert h.starts[-1] == ("owned-compute", 7)
        final = facade.yield_active(resumed, requeue=False)
        assert json.loads(final.payload_json)["progress"] == 14
        assert all(p.poll() == 0 for p in processes.values())
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                stream.close()


def test_status_is_a_detached_observation(h):
    h.request("a")
    report = h.arbiter.status()
    report["events"][0]["request_id"] = "foreign"
    assert h.arbiter.status()["events"][0]["request_id"] == "a"
