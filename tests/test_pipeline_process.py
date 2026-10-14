"""Real owned children, durable checkpoints and full-tree exit, with fixture admission.

These tests never profile a model or start an existing queue/service.
"""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from ocean_resources import (
    BACHFacade,
    CapacityReadback,
    Hold,
    HostLocalArbiter,
    HostWriterAuthority,
    ResourceSocket,
    SlotRequest,
)
from ocean_resources.process import OwnedProcessExecutor, ProcessCommand
from tools import windows_job


WORKER = r"""
import json,os,time,hashlib
from pathlib import Path
root=Path(os.environ["OCEAN_RESOURCE_RUN_DIR"])
start=json.loads((root/"start.json").read_text())
identity={k:start[k] for k in ("schema","grant","execution_identity")}
step=0 if start["resume"] is None else start["resume"]["step"]
memory=bytearray(1024*1024)
def write(name,value):
 p=root/(name+".tmp");p.write_text(json.dumps(value));p.replace(root/name)
write("ready.json",identity)
while not (root/"checkpoint.request.json").exists():time.sleep(.01)
step+=7
payload={"step":step,"digest":hashlib.sha256(str(step).encode()).hexdigest()}
write("checkpoint.json",{**identity,"payload":payload,"quiescent":True})
while True:time.sleep(1)
"""


def make_command(tmp_path, text=WORKER):
    script = tmp_path / "owned_worker.py"
    script.write_text(text, encoding="utf-8")
    executable = Path(sys.executable).resolve()
    pins = tuple((path, hashlib.sha256(path.read_bytes()).hexdigest()) for path in (executable, script))
    env = tuple((key, os.environ[key]) for key in ("SystemRoot", "PATH", "TEMP", "TMP") if key in os.environ)
    return ProcessCommand((str(executable), str(script)), tmp_path.resolve(), pins, env)


def verify(payload):
    return (
        set(payload) == {"step", "digest"}
        and type(payload["step"]) is int
        and payload["digest"] == hashlib.sha256(str(payload["step"]).encode()).hexdigest()
    )


def setup_arbiter(writer):
    sequence = 0

    def capacity():
        nonlocal sequence
        sequence += 1
        return CapacityReadback("owned-test-host", sequence, time.monotonic(), 128, 2, True, True)

    sockets = tuple(ResourceSocket(name, "owned-test-host", 64, 1, "fixture") for name in ("compute", "chat"))
    return HostLocalArbiter(
        writer, sockets, capacity, time.monotonic, fixture_profiles=frozenset({"fixture"}), heartbeat_ttl=30
    )


def test_real_process_checkpoint_exit_chat_and_bit_exact_resume(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        facade = BACHFacade(arbiter, {"compute": executor.adapter(), "chat": executor.adapter()})
        try:
            arbiter.submit(SlotRequest("compute-job", "compute", "compute-slot", "owned-test-host", "compute-key"))
            compute = facade.start_next()
            assert executor.readback(compute, arbiter.status()["execution_identity"]).exited is False
            first = facade.yield_active(compute)
            assert json.loads(first.payload_json)["step"] == 7
            arbiter.submit(SlotRequest("chat-job", "chat", "interactive", "owned-test-host", "chat-key", 1, True))
            chat = facade.start_next()
            facade.yield_active(chat, requeue=False)
            resumed = facade.start_next()
            last = facade.yield_active(resumed, requeue=False)
            assert json.loads(last.payload_json)["step"] == 14
            assert arbiter.status()["torch"] is None
            assert all(run.exited and run.child.poll() is not None for run in executor._executions.values())
        finally:
            executor.close()


def test_checkpoint_validator_failure_does_not_stop_or_release_process(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), lambda payload: False)
        facade = BACHFacade(arbiter, {"compute": executor.adapter()})
        try:
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            with pytest.raises(Hold):
                facade.yield_active(grant)
            assert arbiter.status()["torch"]["request_id"] == "job"
            assert executor._executions[grant].child.poll() is None
        finally:
            executor.close()


def test_mutated_pinned_source_is_blocked_before_spawn(tmp_path):
    command = make_command(tmp_path)
    (tmp_path / "owned_worker.py").write_text("raise SystemExit(1)", encoding="utf-8")
    with pytest.raises(Hold, match="source changed"):
        command.verify_sources()


def test_unpinned_executable_and_mutable_argv_refused(tmp_path):
    command = make_command(tmp_path)
    with pytest.raises(ValueError):
        replace(command, source_pins=command.source_pins[1:])
    with pytest.raises(ValueError):
        replace(command, argv=list(command.argv))


def test_wrong_worker_identity_is_cleaned_without_releasing_arbiter(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    command = make_command(
        tmp_path,
        WORKER.replace(
            'write("ready.json",identity)', 'write("ready.json",{**identity,"execution_identity":"foreign"})'
        ),
    )
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        facade = BACHFacade(arbiter, {"compute": executor.adapter()})
        try:
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            with pytest.raises(Hold):
                facade.start_next()
            assert arbiter.status()["torch"]["request_id"] == "job"
            assert executor._executions == {}
        finally:
            executor.close()


def test_checkpointed_stop_reaps_owned_helper_too(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    text = WORKER.replace(
        'write("ready.json",identity)',
        """import subprocess,sys
helper=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"])
(root/"helper.pid").write_text(str(helper.pid))
write("ready.json",identity)""",
    )
    command = make_command(tmp_path, text)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            run = executor._executions[grant]
            helper_pid = int((run.directory / "helper.pid").read_text())
            facade.yield_active(grant, requeue=False)
            assert run.child.poll() is not None
            if os.name == "nt":
                assert windows_job.process_is_alive(helper_pid) is False
            else:
                with pytest.raises(ProcessLookupError):
                    os.kill(helper_pid, 0)


def test_unacknowledged_checkpoint_keeps_job_and_reservation(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    text = WORKER.replace('write("checkpoint.json",{**identity,"payload":payload,"quiescent":True})', "pass")
    command = make_command(tmp_path, text)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify, timeout_seconds=1) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            with pytest.raises(Hold, match="timed out"):
                facade.yield_active(grant)
            assert executor._executions[grant].child.poll() is None
            assert arbiter.status()["torch"] is not None


@pytest.mark.parametrize("payload", ['{"x":1,"x":2}', '{"x":NaN}', "[]"])
def test_invalid_worker_messages_are_rejected(tmp_path, payload):
    path = tmp_path / "response.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(Hold):
        OwnedProcessExecutor._message(path)


def test_accepted_checkpoint_is_persisted_and_corruption_prevents_stop(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            eid = arbiter.status()["execution_identity"]
            checkpoint = executor.checkpoint(grant, eid)
            path = executor._executions[grant].directory / "accepted.checkpoint.json"
            assert json.loads(path.read_text())["payload_sha256"] == checkpoint.payload_sha256
            path.write_text("{}", encoding="utf-8")
            with pytest.raises(Hold, match="persisted"):
                executor.stop(grant, eid, checkpoint)
            assert executor._executions[grant].child.poll() is None


@pytest.mark.skipif(os.name != "nt", reason="Windows suspended child assignment")
def test_failed_job_assignment_reaps_the_unassigned_suspended_child(tmp_path, monkeypatch):
    import ocean_resources.process as process

    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    created = []
    native_popen = process.subprocess.Popen

    def record(*args, **kwargs):
        child = native_popen(*args, **kwargs)
        created.append(child)
        return child

    def refuse(*args):
        raise windows_job.WindowsJobError("isolated simulated assignment failure")

    monkeypatch.setattr(process.subprocess, "Popen", record)
    monkeypatch.setattr(windows_job, "assign_and_resume", refuse)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            with pytest.raises(Hold):
                facade.start_next()
            assert len(created) == 1 and created[0].poll() is not None
            assert arbiter.status()["torch"] is not None
