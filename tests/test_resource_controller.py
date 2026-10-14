"""Host focus behaviour with injected native ports, no production job mutation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import json
from threading import Event

import pytest

from ocean_resources import (BACHFacade, CapacityReadback, Checkpoint, ComputeExecutorAdapter,
                             ExitReadback, Grant, Hold, HostLocalArbiter, HostWriterAuthority,
                             ResourceSocket, SlotRequest)
from ocean_resources.controller import (ControllerAudit, ControllerClient, FocusPolicy,
                                        HostController, OverrideCommand)
import ocean_resources.controller as controller_module


class FocusHarness:
    def __init__(self, root, *, audit=None):
        self.now, self.sequence = 100.0, 0
        self.writer = HostWriterAuthority(root.resolve(), "focus-host").__enter__()
        sockets = tuple(ResourceSocket(s, "focus-host", 64, 1, "fixture") for s in ("compute", "model", "media"))
        self.arbiter = HostLocalArbiter(self.writer, sockets, self.measure, lambda: self.now,
                                       fixture_profiles=frozenset({"fixture"}))
        self.progress, self.running, self.starts = {}, {}, []
        self.bad_capacity, self.bad_start = False, False
        self.before_checkpoint = lambda: None
        self.adapter = ComputeExecutorAdapter(self.start, self.checkpoint, self.stop, self.readback)
        self.facade = BACHFacade(self.arbiter, {s.socket_id: self.adapter for s in sockets})
        self.operator = ControllerClient("operator", frozenset({"compute", "model", "media"}), operator=True,
                                         allow_interactive=True)
        self.compute = ControllerClient("compute-worker", frozenset({"compute", "media"}))
        self.chat = ControllerClient("chat", frozenset({"model"}), allow_interactive=True)
        self.controller = HostController(self.facade, (self.operator, self.compute, self.chat),
                                         FocusPolicy(2, 5, 3), audit=audit)

    def auth(self, client=None):
        c = self.operator if client is None else client
        return c.client_id, c.token

    def measure(self):
        self.sequence += 1
        return CapacityReadback("focus-host", self.sequence, self.now, 128, 2, True, not self.bad_capacity)

    def submit(self, name, *, interactive=False, priority=3, socket=None):
        client = self.chat if interactive else self.compute
        request = SlotRequest(name, socket or ("model" if interactive else "compute"), name + "-slot",
                              "focus-host", name + "-key", priority, interactive)
        self.controller.submit(*self.auth(client), request)
        return request

    def tick(self, advance=0):
        self.now += advance
        return self.controller.tick(*self.auth())

    def grant(self):
        return Grant(**self.controller.status(*self.auth())["torch"])

    def start(self, grant, request, checkpoint, execution):
        if self.bad_start:
            return False
        self.progress[request.request_id] = 0 if checkpoint is None else json.loads(checkpoint.payload_json)["step"]
        self.running[execution] = True
        self.starts.append((request.request_id, self.progress[request.request_id]))
        return True

    def checkpoint(self, grant, execution):
        self.before_checkpoint()
        return Checkpoint.create(grant, {"step": self.progress[grant.request_id]})

    def stop(self, grant, execution, checkpoint):
        self.running[execution] = False

    def readback(self, grant, execution):
        return ExitReadback(grant, execution, not self.running[execution], 0, self.now)


@pytest.fixture
def focus(tmp_path):
    h = FocusHarness(tmp_path)
    try:
        yield h
    finally:
        h.writer.__exit__()


def test_automatic_checkpoint_chat_idle_and_resume_without_phantom_chat(focus):
    h = focus
    h.submit("compute")
    assert h.tick()["state"] == "RUNNING"
    h.progress["compute"] = 7
    h.submit("telegram", interactive=True, priority=1)
    assert h.tick()["torch"]["request_id"] == "telegram"
    chat = h.grant()
    h.controller.begin_turn(*h.auth(h.chat), chat, "turn-1")
    h.controller.end_turn(*h.auth(h.chat), chat, "turn-1")
    assert h.tick(2)["torch"]["request_id"] == "compute"
    assert h.starts[-1] == ("compute", 7)
    assert all(r["request_id"] != "telegram" for r in h.controller.status(*h.auth())["waiting"])
    assert h.tick(2)["torch"]["request_id"] == "compute"


def test_active_turn_finishes_before_preemption_and_cannot_renew_return(focus):
    h = focus
    h.submit("chat", interactive=True)
    h.tick()
    grant = h.grant()
    h.controller.begin_turn(*h.auth(h.chat), grant, "inference")
    h.submit("compute")
    state = h.tick(5)
    assert state["state"] == "RETURN_REQUESTED" and len(h.starts) == 1
    with pytest.raises(Hold, match="return requested"):
        h.controller.begin_turn(*h.auth(h.chat), grant, "another")
    h.controller.end_turn(*h.auth(h.chat), grant, "inference")
    assert h.tick()["torch"]["request_id"] == "compute"


def test_continuous_chat_has_real_background_runtime_after_burst(focus):
    h = focus
    h.submit("background")
    for n in range(4):
        h.submit("chat-" + str(n), interactive=True, priority=1)
    for n in range(3):
        assert h.tick()["torch"]["request_id"] == "chat-" + str(n)
        h.controller.finish(*h.auth(h.chat), h.grant())
    state = h.controller.status(*h.auth())
    assert state["torch"]["request_id"] == "background"
    assert h.tick()["torch"]["request_id"] == "background"
    assert h.tick(2.9)["torch"]["request_id"] == "background"
    assert h.tick(.1)["torch"]["request_id"] == "chat-3"
    assert [name for name, _ in h.starts].count("background") == 1


def test_idle_without_waiters_releases_and_never_restarts(focus):
    h = focus
    h.submit("chat", interactive=True)
    h.tick()
    assert h.tick(2)["state"] == "IDLE"
    for _ in range(3):
        assert h.tick(1)["state"] == "IDLE"
    assert len(h.starts) == 1


def test_capacity_failure_after_stop_retries_the_same_handoff(focus):
    h = focus
    h.submit("compute")
    h.tick()
    original = h.grant()
    h.progress["compute"] = 9
    h.submit("chat", interactive=True)
    h.bad_capacity = True
    held = h.tick()
    assert held["state"] == "HOLD" and held["torch"] == asdict(original)
    assert not any(h.running.values()) and len(h.starts) == 1
    with pytest.raises(Hold, match="original requeue"):
        h.controller.finish(*h.auth(h.compute), original)
    h.bad_capacity = False
    assert h.tick()["torch"]["request_id"] == "chat"
    h.controller.finish(*h.auth(h.chat), h.grant())
    assert h.starts[-1] == ("compute", 9)


def test_start_capacity_failure_is_retryable_but_failed_executor_is_not_adopted(focus):
    h = focus
    h.submit("job")
    h.bad_capacity = True
    assert h.tick()["state"] == "HOLD" and not h.starts
    h.bad_capacity = False
    h.bad_start = True
    held = h.tick()
    assert held["state"] == "HOLD" and held["torch"] is not None
    assert h.writer.unresolved() is not None
    h.bad_start = False
    assert h.tick()["state"] == "HOLD" and not h.starts


def test_checkpoint_callback_can_report_status_and_submit_from_another_thread(focus):
    h = focus
    h.submit("compute")
    h.tick()
    h.submit("chat", interactive=True)
    def callback():
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(h.controller.status, *h.auth()).result(timeout=2)
            assert result["state"] == "TRANSITION"
    h.before_checkpoint = callback
    assert h.tick()["torch"]["request_id"] == "chat"


def test_overlapping_ticks_do_not_run_two_lifecycle_transitions(focus):
    h = focus
    h.submit("compute")
    h.tick()
    h.submit("chat", interactive=True)
    entered, release = Event(), Event()
    def checkpoint():
        entered.set()
        assert release.wait(3)
    h.before_checkpoint = checkpoint
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(h.tick)
        assert entered.wait(2)
        try:
            assert h.tick()["state"] == "TRANSITION"
            assert len(h.starts) == 1
        finally:
            release.set()
        assert future.result(timeout=3)["torch"]["request_id"] == "chat"


def command(h, name="override", request="media", **changes):
    return replace(OverrideCommand(name, "focus-host", h.writer.authority_id, request, "user focus", h.now + 10), **changes)


def test_override_requires_operator_and_bound_session_and_is_not_renewed_by_replay(focus):
    h = focus
    h.submit("chat", interactive=True)
    h.tick()
    h.submit("media", socket="media", priority=4)
    value = command(h)
    with pytest.raises(Hold, match="operator"):
        h.controller.override(*h.auth(h.compute), value)
    with pytest.raises(Hold, match="foreign"):
        h.controller.override(*h.auth(), replace(value, authority_id="other-session"))
    h.controller.override(*h.auth(), value)
    h.controller.override(*h.auth(), value)
    with pytest.raises(Hold, match="identity conflict"):
        h.controller.override(*h.auth(), replace(value, expires_at=value.expires_at + 1))
    assert h.tick()["torch"]["request_id"] == "media"
    h.controller.override(*h.auth(), value)  # Consumed command must not be applied again.
    assert h.controller.status(*h.auth())["override"] is None
    audit = (h.writer.directory / "focus-host.focus-audit.jsonl").read_text()
    assert audit.count('"override-requested"') == 1
    assert all(c.token not in audit for c in (h.operator, h.chat, h.compute))


@pytest.mark.parametrize("field,value", [("expires_at", 99), ("expires_at", 161), ("host_id", "foreign")])
def test_invalid_override_never_changes_selection(focus, field, value):
    h = focus
    h.submit("media", socket="media")
    with pytest.raises(Hold):
        h.controller.override(*h.auth(), command(h, **{field: value}))
    assert h.arbiter.status()["override"] is None


def test_client_auth_scope_ownership_and_secrets_in_repr(focus):
    h = focus
    with pytest.raises(Hold, match="authentication"):
        h.controller.status("operator", "wrong")
    with pytest.raises(Hold, match="scope"):
        h.controller.submit(*h.auth(h.compute), SlotRequest("bad", "model", "slot", "focus-host", "bad-key"))
    h.submit("chat", interactive=True)
    h.tick()
    with pytest.raises(Hold, match="does not own"):
        h.controller.finish(*h.auth(h.compute), h.grant())
    assert h.operator.token not in repr(h.operator)


def test_expired_heartbeat_never_implicitly_clears_residency(focus):
    h = focus
    h.submit("job")
    h.tick()
    original = h.grant()
    h.before_checkpoint = lambda: (_ for _ in ()).throw(Hold("not quiescent"))
    held = h.tick(11)
    assert held["state"] == "HOLD" and held["torch"] == asdict(original)
    assert any(h.running.values()) and h.writer.unresolved() is not None


def test_second_controller_and_foreign_process_fail_closed(focus, monkeypatch):
    h = focus
    with pytest.raises(Hold, match="already bound"):
        HostController(h.facade, (h.operator,))
    monkeypatch.setattr(controller_module.os, "getpid", lambda: -1)
    with pytest.raises(Hold, match="foreign controller process"):
        h.controller.status(*h.auth())


def test_audit_failure_refuses_override_before_mutation(focus):
    h = focus
    h.submit("media", socket="media")
    h.controller._audit_sink = lambda event: (_ for _ in ()).throw(OSError("private/path"))
    with pytest.raises(Hold, match="audit unavailable"):
        h.controller.override(*h.auth(), command(h))
    assert h.arbiter.status()["override"] is None


def test_default_controller_audit_is_durable(focus):
    h = focus
    audit = ControllerAudit(h.writer)
    audit({"event": "test"})
    assert json.loads(audit.path.read_text()) == {"event": "test"}


def test_real_owned_process_automatic_handoff_and_checkpoint_resume(tmp_path):
    from test_pipeline_process import make_command, setup_arbiter, verify
    from ocean_resources.process import OwnedProcessExecutor
    state = tmp_path / "state"
    state.mkdir()
    command_spec = make_command(tmp_path)
    with HostWriterAuthority(state.resolve(), "owned-test-host") as writer:
        arbiter = setup_arbiter(writer)  # Synthetic admission, real owned OS children.
        executor = OwnedProcessExecutor(arbiter, command_spec, state.resolve(), verify)
        facade = BACHFacade(arbiter, {"compute": executor.adapter(), "chat": executor.adapter()})
        operator = ControllerClient("operator", frozenset({"compute", "chat"}), operator=True, allow_interactive=True)
        auth = operator.client_id, operator.token
        ctl = HostController(facade, (operator,))
        try:
            ctl.submit(*auth, SlotRequest("compute", "compute", "compute-slot", "owned-test-host", "compute-key"))
            assert ctl.tick(*auth)["torch"]["request_id"] == "compute"
            ctl.submit(*auth, SlotRequest("chat", "chat", "chat-slot", "owned-test-host", "chat-key", 1, True))
            assert ctl.tick(*auth)["torch"]["request_id"] == "chat"
            assert json.loads(arbiter.checkpoint_for("compute").payload_json)["step"] == 7
            chat = Grant(**ctl.status(*auth)["torch"])
            assert ctl.finish(*auth, chat)["torch"]["request_id"] == "compute"
            compute = Grant(**ctl.status(*auth)["torch"])
            assert ctl.finish(*auth, compute)["state"] == "IDLE"
            assert json.loads(arbiter.checkpoint_for("compute").payload_json)["step"] == 14
            assert writer.unresolved() is None
            assert all(run.exited and run.child.poll() is not None for run in executor._executions.values())
        finally:
            executor.close()
