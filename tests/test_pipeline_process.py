"""Real owned children, durable checkpoints and full-tree exit, with fixture admission.

These tests never profile a model or start an existing queue/service.
"""

from dataclasses import asdict, replace
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


def test_process_and_checkpoint_evidence_are_durable_before_handoff(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    text = WORKER.replace(
        "memory=bytearray(1024*1024)",
        "(root/\"application.started\").touch()\nmemory=bytearray(1024*1024)",
    )
    command = make_command(tmp_path, text)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        process_time_reads = []
        phases = []

        def process_times(pid):
            process_time_reads.append(pid)
            return 1000.0, 900.0

        def capture_before_gate(grant, evidence):
            marker = Path(evidence["run_directory"]) / "application.started"
            assert not marker.exists(), "application ran before durable gate evidence"
            original_execution_record(grant, evidence)
            saved = writer.unresolved()
            assert saved["execution_evidence"]["gate_state"] == evidence["gate_state"]
            phases.append(evidence["gate_state"])

        original_execution_record = arbiter.record_execution_evidence
        arbiter.record_execution_evidence = capture_before_gate
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            executor._process_times = process_times
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            run = executor._executions[grant]
            assert phases == ["closed", "may-open"]
            assert process_time_reads == [run.child.pid]
            assert (run.directory / "application.started").is_file()

            accepted = executor.checkpoint(grant, run.identity)
            saved = writer.unresolved()
            evidence = saved["checkpoint_evidence"]
            checkpoint_file = Path(evidence["checkpoint_file"])
            assert evidence["payload_sha256"] == accepted.payload_sha256
            assert hashlib.sha256(checkpoint_file.read_bytes()).hexdigest() == evidence["checkpoint_file_sha256"]
            assert run.child.poll() is None, "checkpoint evidence must be durable before stop"

            assert facade.yield_active(grant, requeue=False) == accepted
            assert writer.unresolved() is None


def test_stop_requires_checkpoint_evidence_after_journal_write_failure(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        original_record = writer.record

        def fail_checkpoint_record(unresolved):
            if unresolved is not None and unresolved.get("checkpoint_evidence") is not None:
                raise Hold("simulated checkpoint journal fsync failure")
            original_record(unresolved)

        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            run = executor._executions[grant]
            monkeypatch.setattr(writer, "record", fail_checkpoint_record)

            with pytest.raises(Hold, match="simulated checkpoint journal fsync failure"):
                executor.checkpoint(grant, run.identity)
            assert run.accepted is not None
            assert writer.unresolved()["checkpoint_evidence"] is None

            with pytest.raises(Hold, match="simulated checkpoint journal fsync failure"):
                executor.stop(grant, run.identity, run.accepted)
            assert run.child.poll() is None, "stop must not proceed without the durable journal binding"


def test_checkpoint_evidence_uses_bounded_file_snapshot(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            run = executor._executions[grant]
            accepted = executor.checkpoint(grant, run.identity)
            checkpoint_file = run.directory / "accepted.checkpoint.json"

            checkpoint_file.write_bytes(b"x" * (1024 * 1024 + 1))
            with pytest.raises(Hold, match="accepted checkpoint evidence exceeds bound"):
                executor.stop(grant, run.identity, accepted)
            assert run.child.poll() is None, "an oversized checkpoint must not stop the owned process"

            checkpoint_file.write_text(json.dumps(asdict(accepted), sort_keys=True), encoding="utf-8")
            original_read_bytes = Path.read_bytes

            def reject_unbounded_checkpoint_read(path):
                if path == checkpoint_file:
                    raise AssertionError("accepted checkpoint must use a bounded stream read")
                return original_read_bytes(path)

            monkeypatch.setattr(Path, "read_bytes", reject_unbounded_checkpoint_read)
            assert facade.yield_active(grant, requeue=False) == accepted
            assert writer.unresolved() is None


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


def test_release_retry_uses_verified_exit_without_signalling_again(tmp_path, monkeypatch):
    import ocean_resources.process as process

    state = tmp_path / "state"
    state.mkdir()
    command = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        with OwnedProcessExecutor(arbiter, command, state.resolve(), verify) as executor:
            facade = BACHFacade(arbiter, {"compute": executor.adapter()})
            arbiter.submit(SlotRequest("job", "compute", "slot", "owned-test-host", "key"))
            grant = facade.start_next()
            capacity = arbiter._sensor
            monkeypatch.setattr(arbiter, "_sensor", lambda: replace(capacity(), available_ram_bytes=None))
            with pytest.raises(Hold):
                facade.yield_active(grant, requeue=False)
            assert executor._executions[grant].exited
            assert arbiter.status()["torch"] is not None

            def refuse_signal(*args, **kwargs):
                raise AssertionError("verified exit must not signal an old process identity")

            monkeypatch.setattr(process, "_terminate_child", refuse_signal)
            monkeypatch.setattr(arbiter, "_sensor", capacity)
            checkpoint = facade.yield_active(grant, requeue=False)
            assert json.loads(checkpoint.payload_json)["step"] == 7
            assert arbiter.status()["torch"] is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap pipe and SIGCHLD semantics")
@pytest.mark.parametrize("capture_fails", [False, True])
def test_posix_application_cannot_start_before_fence_even_with_sigchld_ignored(tmp_path, capture_fails):
    # SIGCHLD disposition changes only inside this isolated test process.
    import subprocess

    probe = r'''
import os, runpy, signal, sys, time
from pathlib import Path
fixture = runpy.run_path(sys.argv[1])
globals().update({k: fixture[k] for k in (
 "make_command", "WORKER", "HostWriterAuthority", "setup_arbiter",
 "OwnedProcessExecutor", "BACHFacade", "SlotRequest", "Hold", "verify")})
import ocean_resources.process as process
root=Path(sys.argv[2]); state=root/"state"; state.mkdir()
signal.signal(signal.SIGCHLD, signal.SIG_IGN)
command=make_command(root, WORKER.replace('step=0 if', '(root/"application.started").touch()\nstep=0 if'))
native=process._capture_posix_process_fence
capture_fails=sys.argv[3]=="True"
def capture(pid):
 time.sleep(.3)
 assert not list(state.glob("*/application.started")), "application ran before fence"
 if capture_fails: raise RuntimeError("isolated capture failure")
 return native(pid)
process._capture_posix_process_fence=capture
with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
 arbiter=setup_arbiter(writer)
 with OwnedProcessExecutor(arbiter,command,state.resolve(),verify,timeout_seconds=2) as executor:
  facade=BACHFacade(arbiter,{"compute":executor.adapter()})
  arbiter.submit(SlotRequest("job","compute","slot","owned-test-host","key"))
  if capture_fails:
   try: facade.start_next()
   except Hold: pass
   else: raise AssertionError("failed fence unexpectedly started")
   assert not list(state.glob("*/application.started"))
   assert not executor._executions
   assert arbiter.status()["torch"] is not None
  else:
   grant=facade.start_next()
   facade.yield_active(grant,requeue=False)
   assert arbiter.status()["torch"] is None
'''
    completed = subprocess.run(
        [sys.executable, "-c", probe, str(Path(__file__).resolve()), str(tmp_path.resolve()), str(capture_fails)],
        capture_output=True, text=True, timeout=15,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
