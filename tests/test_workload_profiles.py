"""Pinned profile policy and real own-process binding, without production jobs."""
from dataclasses import replace
import asyncio
from contextlib import asynccontextmanager
import hashlib
from importlib import util
import json
import os
import platform
import subprocess
import sys
import time

import pytest

from ocean_resources import (BACHFacade, CapacityReadback, ComputeExecutorAdapter, Hold,
                             HostLocalArbiter, HostWriterAuthority, ResourceSocket, SlotRequest)
from ocean_resources.process import OwnedProcessExecutor
from ocean_resources.profiles import ProfileSource, ReviewedProfileGate, native_architecture


def write_json(path, value):
    content = json.dumps(value, sort_keys=True, allow_nan=True).encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def documents(tmp_path):
    evidence = {"schema": "ocean-workload-measurement.v1", "scope": "cpu-process-tree",
                "method": "sampled-rss-and-cumulative-cpu-v1", "host_id": platform.node(),
                "platform": platform.system(), "architecture": native_architecture(), "workload_sha256": "a" * 64,
                "peak_rss_bytes": 60, "peak_cpu_units": 0.5, "cpu_concurrency_units": 1,
                "sample_count": 3, "sample_interval_seconds": 0.1, "started_at": 900.0, "finished_at": 901.0,
                "exit_verified": True, "checkpoint_verified": True, "unmeasured_external_residency": False}
    profile = {"schema": "ocean-reviewed-workload-profile.v1", "kind": "cpu-owned-process", "profile_id": "reviewed",
               "socket_id": "compute", "host_id": platform.node(), "platform": platform.system(),
               "architecture": native_architecture(), "workload_sha256": "a" * 64,
               "ram_bytes": 100, "cpu_units": 1, "ram_margin_bytes": 20, "evidence_sha256": "b" * 64,
               "approved_by": "operator", "approved_at": 902.0, "expires_at": 2000.0}
    return {"profile": profile, "evidence": evidence, "root": tmp_path.resolve(), "now": [1000.0]}


def source_for(data):
    root = data["root"]
    data["profile"]["evidence_sha256"] = write_json(root / "evidence.json", data["evidence"])
    pin = write_json(root / "profile.json", data["profile"])
    return ProfileSource(root / "profile.json", pin, root / "evidence.json")


def socket_for(data):
    p = data["profile"]
    return ResourceSocket(p["socket_id"], p["host_id"], p["ram_bytes"], p["cpu_units"], p["profile_id"], p["workload_sha256"])


def gate_for(data):
    return ReviewedProfileGate((source_for(data),), max_age_seconds=200, wall_clock=lambda: data["now"][0])


def test_explicit_pinned_profile_and_measurement_match_full_socket(documents):
    gate = gate_for(documents)
    profile = gate.require(socket_for(documents))
    assert profile["ram_bytes"] == 100 and profile["kind"] == "cpu-owned-process"
    # Detached results cannot edit the configured allowlist.
    profile["ram_bytes"] = 999
    assert gate.require(socket_for(documents))["ram_bytes"] == 100


@pytest.mark.parametrize("key,value", [
    ("host_id", "foreign"), ("platform", "foreign"), ("architecture", "foreign"),
    ("schema", "untrusted"), ("kind", "model-api"), ("ram_bytes", True),
    ("cpu_units", 0), ("ram_margin_bytes", 0), ("ram_bytes", 79),
    ("workload_sha256", "invalid"), ("approved_at", 899), ("approved_at", 1001),
    ("expires_at", 999), ("expires_at", float("nan")),
])
def test_unapproved_or_inconsistent_profile_fields_are_rejected(documents, key, value):
    documents["profile"][key] = value
    with pytest.raises(ValueError):
        gate_for(documents)


@pytest.mark.parametrize("key,value", [
    ("workload_sha256", "c" * 64), ("host_id", "foreign"), ("scope", "model-daemon"),
    ("exit_verified", False), ("exit_verified", 1), ("checkpoint_verified", False),
    ("unmeasured_external_residency", True), ("peak_rss_bytes", None),
    ("peak_cpu_units", float("inf")), ("cpu_concurrency_units", 2), ("peak_cpu_units", 1.1),
    ("sample_count", True), ("sample_count", 1), ("sample_count", 10**400),
    ("sample_interval_seconds", 1e308), ("sample_interval_seconds", 20),
    ("started_at", 902), ("finished_at", 1001),
])
def test_incomplete_or_unsupported_native_evidence_stays_closed(documents, key, value):
    documents["evidence"][key] = value
    with pytest.raises(ValueError):
        gate_for(documents)


@pytest.mark.parametrize("key,value", [("ram_bytes", 99), ("cpu_units", 2), ("workload_sha256", "c" * 64),
                                       ("profile_id", "other"), ("socket_id", "other"), ("host_id", "foreign")])
def test_approval_cannot_be_reused_for_another_socket_or_demand(documents, key, value):
    gate = gate_for(documents)
    socket = replace(socket_for(documents), **{key: value})
    with pytest.raises(Hold):
        gate.require(socket)


@pytest.mark.parametrize("name", ["profile.json", "evidence.json"])
def test_changed_pinned_bytes_fail_even_if_semantics_or_embedded_approval_look_valid(documents, name):
    gate = gate_for(documents)
    path = documents["root"] / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(Hold):
        gate.require(socket_for(documents))


def test_policy_rejects_duplicate_json_keys_and_extra_self_approval(documents):
    source = source_for(documents)
    raw = source.profile_path.read_bytes().replace(b'"cpu_units": 1', b'"cpu_units": 1, "cpu_units": 1')
    source.profile_path.write_bytes(raw)
    source = replace(source, profile_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="duplicate"):
        ReviewedProfileGate((source,), max_age_seconds=200)
    documents["profile"]["reviewed"] = True
    with pytest.raises(ValueError, match="exact"):
        gate_for(documents)


def test_expiry_staleness_nonfinite_clock_and_foreign_pid_cannot_authorize(documents, monkeypatch):
    gate = gate_for(documents)
    for now in (1102, 2000, 899, float("nan")):
        documents["now"][0] = now
        with pytest.raises(Hold):
            gate.require(socket_for(documents))
    documents["now"][0] = 1000
    monkeypatch.setattr(os, "getpid", lambda: -1)
    with pytest.raises(Hold):
        gate.require(socket_for(documents))


def test_default_gate_closed_then_reviewed_acquire_checks_adapter_binding(documents, tmp_path):
    gate = gate_for(documents)
    socket = socket_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    sequence = [0]
    def sensor():
        sequence[0] += 1
        return CapacityReadback(platform.node(), sequence[0], time.monotonic(), 1000, 2, True, True)
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket,), sensor, time.monotonic, profile_gate=gate)
        arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
        calls = []
        adapter = ComputeExecutorAdapter(lambda *args: calls.append(args), lambda *a: None,
                                         lambda *a: None, lambda *a: None, "c" * 64, "cpu-owned-process")
        facade = BACHFacade(arbiter, {"compute": adapter})
        with pytest.raises(Hold, match="workload"):
            facade.start_next()
        assert calls == [] and arbiter.status()["torch"] is not None


def test_process_fingerprint_binds_arguments_workdir_pins_and_environment(tmp_path):
    from test_pipeline_process import make_command
    command = make_command(tmp_path)
    changed = tmp_path / "other"
    changed.mkdir()
    variants = (replace(command, argv=(*command.argv, "another-input")), replace(command, cwd=changed.resolve()),
                replace(command, source_pins=(*command.source_pins[:-1], (command.source_pins[-1][0], "a" * 64))),
                replace(command, environment=(*command.environment, ("OTHER_INPUT", "private-value"))))
    assert all(c.fingerprint() != command.fingerprint() for c in variants)
    assert len(command.fingerprint()) == 64 and "private-value" not in command.fingerprint()
    with pytest.raises(ValueError):
        replace(command, environment=(("OCEAN_RESOURCE_RUN_DIR", "forged"),))


def test_profile_cli_validates_pins_without_grant_or_file_writes(documents):
    now = time.time()
    documents["evidence"].update(started_at=now - 3, finished_at=now - 2)
    documents["profile"].update(approved_at=now - 1, expires_at=now + 120)
    source = source_for(documents)
    before = {p.name: p.read_bytes() for p in documents["root"].iterdir()}
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-m", "ocean_resources", "profiles", "--profile", str(source.profile_path),
               "--profile-sha256", source.profile_sha256, "--evidence", str(source.evidence_path),
               "--profile-max-age-seconds", "60"]
    process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=20)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["state"] == "VALIDATED" and report["start_authorized"] is False
    assert report["models_started"] == report["queue_writes"] == 0
    assert before == {p.name: p.read_bytes() for p in documents["root"].iterdir()}
    source.evidence_path.write_text("{}")
    failed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=20)
    assert failed.returncode == 2 and json.loads(failed.stdout)["state"] == "HOLD"


def test_actual_owned_command_uses_profile_and_expiry_still_allows_checkpoint_exit(documents, tmp_path):
    from test_pipeline_process import make_command, verify
    command = replace(make_command(tmp_path), source_mode="frozen-python")
    documents["profile"]["workload_sha256"] = command.fingerprint()
    documents["evidence"]["workload_sha256"] = command.fingerprint()
    gate = gate_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    sequence = [0]
    def sensor():
        sequence[0] += 1
        return CapacityReadback(platform.node(), sequence[0], time.monotonic(), 1000, 2, True, True)
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket_for(documents),), sensor, time.monotonic, profile_gate=gate,
                                   heartbeat_ttl=30)
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        facade = BACHFacade(arbiter, {"compute": executor.adapter()})
        try:
            arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
            grant = facade.start_next()
            assert arbiter.status()["mode"] == "reviewed-workload-profiles"
            if util.find_spec("psutil") is not None:
                import psutil
                if (5, 9, 6) <= psutil.version_info < (8,):
                    usage = executor.measure_usage(grant, arbiter.status()["execution_identity"])
                    assert usage["rss_bytes"] > 0 and usage["members"][0]["pid"] > 0
                    assert usage["cpu_seconds"] >= 0 and usage["grant"]["request_id"] == "job"
            documents["now"][0] = 2000
            with pytest.raises(Hold):
                arbiter.heartbeat(grant)
            checkpoint = facade.yield_active(grant)
            assert json.loads(checkpoint.payload_json)["step"] == 7
            assert arbiter.status()["torch"] is None and writer.unresolved() is None
            with pytest.raises(Hold):
                facade.start_next()
            assert len(executor._executions) == 1
            with pytest.raises(Hold):
                executor.measure_usage(grant, "not-this-execution")
        finally:
            executor.close()


def test_profile_changed_after_acquire_never_starts_application(documents, tmp_path):
    from test_pipeline_process import make_command, verify
    command = make_command(tmp_path)
    for key in ("profile", "evidence"):
        documents[key]["workload_sha256"] = command.fingerprint()
    gate = gate_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket_for(documents),),
            lambda: CapacityReadback(platform.node(), 1, time.monotonic(), 1000, 2, True, True),
            time.monotonic, profile_gate=gate)
        arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
        grant = arbiter.acquire()
        arbiter.bind_execution(grant, "execution")
        documents["root"].joinpath("evidence.json").write_text("{}")
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        with pytest.raises(Hold):
            executor.start(grant, arbiter.request_for(grant), None, "execution")
        assert executor._executions == {} and list(state.iterdir()) == [state / (platform.node() + ".writer")]


def test_cpu_process_profile_never_authorizes_a_model_daemon(documents, tmp_path):
    from ocean_resources import ModelSocketBinding, ModelSocketInferenceAdapter
    gate = gate_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    class NativeModelGate:
        @asynccontextmanager
        async def turn(self, *args, **kwargs):
            pytest.fail("CPU process profile reached a model backend")
            yield
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket_for(documents),),
            lambda: CapacityReadback(platform.node(), 1, time.monotonic(), 1000, 2, True, True),
            time.monotonic, profile_gate=gate)
        arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
        grant = arbiter.acquire()
        model = ModelSocketInferenceAdapter(arbiter,
            ModelSocketBinding("compute", "binding", "agent", "ollama", "not-profiled"), NativeModelGate())
        async def attempt():
            async with model.turn(grant, "chat"):
                pytest.fail("model inference was authorized")
        with pytest.raises(Hold, match="kind"):
            asyncio.run(attempt())


def test_foreign_arbiter_and_executor_reject_before_inherited_mutex_and_never_signal_parent(tmp_path, monkeypatch):
    from test_pipeline_process import make_command, setup_arbiter, verify
    class InheritedMutex:
        def __enter__(self):
            pytest.fail("foreign process entered an inherited mutex")
        def __exit__(self, *args):
            pass
    state = tmp_path / "state"
    state.mkdir()
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)
        executor = OwnedProcessExecutor(arbiter, make_command(tmp_path), state.resolve(), verify)
        arbiter._mutex = executor._mutex = InheritedMutex()
        with monkeypatch.context() as context:
            context.setattr(os, "getpid", lambda: -1)
            for call in (arbiter.status, lambda: executor.readback(None, "foreign"),
                         lambda: executor.measure_usage(None, "foreign")):
                with pytest.raises(Hold, match="foreign"):
                    call()
            executor.close()


@pytest.mark.parametrize("mutation_stage", ["start-message", "after-final-verification"])
def test_frozen_application_cannot_execute_replaced_path(documents, tmp_path, monkeypatch, mutation_stage):
    from test_pipeline_process import make_command, verify
    command = replace(make_command(tmp_path), source_mode="frozen-python")
    for key in ("profile", "evidence"):
        documents[key]["workload_sha256"] = command.fingerprint()
    gate = gate_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    sequence = [0]
    marker = tmp_path / "changed-source-executed"
    def mutate():
        (tmp_path / "owned_worker.py").write_text(
            f"from pathlib import Path;Path({str(marker)!r}).write_text('bad')", encoding="utf-8")
    def sensor():
        sequence[0] += 1
        return CapacityReadback(platform.node(), sequence[0], time.monotonic(), 1000, 2, True, True)
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket_for(documents),), sensor, time.monotonic,
                                   profile_gate=gate, heartbeat_ttl=30)
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        facade = BACHFacade(arbiter, {"compute": executor.adapter()})
        arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
        if mutation_stage == "start-message":
            original = executor._write
            def write(path, value):
                original(path, value)
                if path.name == "start.json":
                    mutate()
            monkeypatch.setattr(executor, "_write", write)
        else:
            original = arbiter.prepare_execution
            def prepare(*args, **kwargs):
                original(*args, **kwargs)
                mutate()
            monkeypatch.setattr(arbiter, "prepare_execution", prepare)
        try:
            if mutation_stage == "start-message":
                with pytest.raises(Hold, match="reservation remains held") as rejected:
                    facade.start_next()
                assert "source changed" in str(rejected.value.__cause__)
                assert executor._executions == {}
                assert arbiter.status()["torch"] is not None
            else:
                grant = facade.start_next()
                checkpoint = facade.yield_active(grant, requeue=False)
                assert json.loads(checkpoint.payload_json)["step"] == 7
                assert sequence[0] == 3  # Acquire, activation, verified post-exit.
            assert not marker.exists()
        finally:
            executor.close()


def test_reviewed_activation_requires_frozen_code_and_fresh_sufficient_capacity(documents, tmp_path):
    from test_pipeline_process import make_command, verify
    command = replace(make_command(tmp_path), source_mode="frozen-python")
    for key in ("profile", "evidence"):
        documents[key]["workload_sha256"] = command.fingerprint()
    gate = gate_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    sequence = [0]
    def sensor():
        sequence[0] += 1
        return CapacityReadback(platform.node(), sequence[0], time.monotonic(),
                                1000 if sequence[0] == 1 else 99, 2, True, True)
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket_for(documents),), sensor, time.monotonic, profile_gate=gate)
        arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
        grant = arbiter.acquire()
        with pytest.raises(Hold, match="frozen"):
            arbiter.prepare_execution(grant, command.fingerprint(), source_mode="path-checked")
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        arbiter.bind_execution(grant, "execution")
        try:
            with pytest.raises(Hold, match="fresh capacity"):
                executor.start(grant, arbiter.request_for(grant), None, "execution")
            assert executor._executions == {} and arbiter.status()["torch"] is not None
        finally:
            executor.close()


def test_huge_numeric_measurement_cli_fails_as_json_hold(documents):
    documents["evidence"]["sample_count"] = 10**400
    source = source_for(documents)
    process = subprocess.run([sys.executable, "-m", "ocean_resources", "profiles",
        "--profile", str(source.profile_path), "--profile-sha256", source.profile_sha256,
        "--evidence", str(source.evidence_path), "--profile-max-age-seconds", "200"],
        capture_output=True, text=True, timeout=20)
    assert process.returncode == 2 and json.loads(process.stdout)["state"] == "HOLD"
    assert "Traceback" not in process.stderr


@pytest.mark.parametrize("revocation", ["expire", "evidence"])
def test_profile_revoked_during_capacity_never_activates_frozen_application(documents, tmp_path, revocation):
    from test_pipeline_process import make_command, verify, WORKER
    marker = tmp_path / "application-was-activated"
    text = f"from pathlib import Path;Path({str(marker)!r}).write_text('bad')\n" + WORKER
    command = replace(make_command(tmp_path, text), source_mode="frozen-python")
    for key in ("profile", "evidence"):
        documents[key]["workload_sha256"] = command.fingerprint()
    gate = gate_for(documents)
    state = tmp_path / "state"
    state.mkdir()
    sequence = [0]
    def sensor():
        sequence[0] += 1
        if sequence[0] == 2:
            if revocation == "expire":
                documents["now"][0] = 2000
            else:
                (documents["root"] / "evidence.json").write_text("{}")
        return CapacityReadback(platform.node(), sequence[0], time.monotonic(), 1000, 2, True, True)
    with HostWriterAuthority(state.resolve(), platform.node()) as writer:
        arbiter = HostLocalArbiter(writer, (socket_for(documents),), sensor, time.monotonic, profile_gate=gate)
        executor = OwnedProcessExecutor(arbiter, command, state.resolve(), verify)
        facade = BACHFacade(arbiter, {"compute": executor.adapter()})
        arbiter.submit(SlotRequest("job", "compute", "slot", platform.node(), "key"))
        try:
            with pytest.raises(Hold):
                facade.start_next()
            assert not marker.exists() and executor._executions == {}
            assert arbiter.status()["torch"] is not None
        finally:
            executor.close()


def test_missing_native_architecture_cannot_approve_matching_blank_fields(documents, monkeypatch):
    import ocean_resources.profiles as profiles
    documents["profile"]["architecture"] = documents["evidence"]["architecture"] = ""
    source = source_for(documents)
    monkeypatch.setattr(profiles, "native_architecture", lambda: "")
    with pytest.raises(ValueError, match="identity"):
        ReviewedProfileGate((source,), max_age_seconds=200)


@pytest.mark.skipif(os.name != "nt", reason="Windows native machine API")
def test_windows_profile_architecture_uses_kernel_when_platform_probe_is_blank(documents, monkeypatch):
    expected = native_architecture()
    monkeypatch.setattr(platform, "machine", lambda: "")
    assert native_architecture() == expected
    assert gate_for(documents).require(socket_for(documents))["architecture"] == expected
