"""Actual loopback and separate-process clients; injected fixture executors only."""
from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event, Thread, current_thread
import time
from types import MappingProxyType

import pytest
import ocean_resources

from ocean_resources import Grant, Hold, SlotRequest
from ocean_resources.client import HostClient
from ocean_resources.controller import OverrideCommand
from ocean_resources.service import HostService, LIMIT, SCHEMA, decode_json
from test_resource_controller import FocusHarness


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError("host service did not reach expected state")


def running(client, request_id):
    # A torch may be visible during TRANSITION before its executor is ready.
    state = client.status()
    return state if (state["state"] == "RUNNING"
                     and (state["torch"] or {}).get("request_id") == request_id) else None


@pytest.fixture
def transport(tmp_path):
    harness = FocusHarness(tmp_path)
    service = HostService(harness.controller, harness.operator, tick_seconds=.05)
    loop = Thread(target=service.serve_forever, name="test-owned-host-loop")
    loop.start()
    def client(configured):
        return HostClient(service.port, "focus-host", harness.writer.authority_id,
                          configured.client_id, configured.token)
    try:
        yield harness, service, client
    finally:
        service.close()
        loop.join(2)
        assert not loop.is_alive()
        harness.writer.__exit__()


def test_network_clients_share_one_authority_and_native_request_identity(transport):
    h, service, make_client = transport
    compute, chat, operator = (make_client(c) for c in (h.compute, h.chat, h.operator))
    request = SlotRequest("compute", "compute", "native-slot", "focus-host", "native-key")
    assert compute.submit(request) == compute.submit(request) == "compute"
    wait_for(lambda: running(compute, "compute"))
    h.progress["compute"] = 7
    chat.submit(SlotRequest("telegram", "model", "chat-slot", "focus-host", "chat-key", 1, True))
    ready = wait_for(lambda: running(chat, "telegram"))
    grant = Grant(**ready["torch"])
    chat.begin_turn(grant, "actual-turn")
    assert operator.status()["in_flight_turns"] == 1
    chat.end_turn(grant, "actual-turn")
    h.now += 2
    ready = wait_for(lambda: running(compute, "compute"))
    assert h.starts[-1] == ("compute", 7)
    compute.finish(Grant(**ready["torch"]))
    assert operator.status()["state"] == "IDLE"
    assert not h.controller.status(*h.auth())["waiting"]
    assert service._server.server_address[0] == "127.0.0.1"


def test_separate_python_process_uses_wire_client_without_importing_writer_state(transport):
    h, _, make_client = transport
    client = make_client(h.compute)
    script = """
import json,sys
from ocean_resources.client import HostClient
config=json.loads(sys.stdin.read())
c=HostClient(**config)
print(json.dumps({'host':c.status()['host_id'],'session':c.status()['authority_id']}))
"""
    package_root = Path(ocean_resources.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(package_root), "PYTHONDONTWRITEBYTECODE": "1"}
    # -I deliberately ignores PYTHONPATH: select this test source explicitly.
    bootstrap = "import sys;sys.path.insert(0," + repr(str(package_root)) + ");" + script
    process = subprocess.run([sys.executable, "-I", "-c", bootstrap], input=json.dumps(asdict(client)),
                              capture_output=True, text=True, timeout=15, env=env)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"host": "focus-host", "session": h.writer.authority_id}
    assert client.token not in process.stdout + process.stderr
    assert client.token not in repr(client)


def test_wrong_credentials_writer_epoch_and_permissions_never_submit_or_override(transport):
    h, _, make_client = transport
    client = make_client(h.compute)
    request = SlotRequest("illegal", "model", "slot", "focus-host", "key", 1, True)
    for invalid in (replace(client, token="x" * 32), replace(client, client_id="unknown"),
                    replace(client, authority_id="old-writer"), replace(client, host_id="other-host")):
        with pytest.raises(Hold):
            invalid.status()
    with pytest.raises(Hold):
        client.submit(request)
    with pytest.raises(Hold):
        client.call("tick")
    with pytest.raises(Hold):
        client.override(OverrideCommand("override", "focus-host", h.writer.authority_id,
                                        None, "must be operator", h.now + 10))
    assert not make_client(h.operator).status()["waiting"] and h.starts == []


@pytest.mark.parametrize("case", ["origin", "host", "duplicate", "nonfinite", "chunked", "unknown", "schema"])
def test_malformed_or_browser_origin_messages_have_no_state_changes(transport, case):
    h, service, make_client = transport
    client = make_client(h.compute)
    message = {"schema": SCHEMA, "host_id": "focus-host", "authority_id": h.writer.authority_id, "payload": {}}
    if case == "schema":
        message["schema"] = "untrusted"
    content = json.dumps(message).encode()
    if case == "duplicate":
        content = content.replace(b'"payload": {}', b'"payload": {},"payload": {}')
    if case == "nonfinite":
        content = content.replace(b'"payload": {}', b'"payload": {"unexpected": NaN}')
    headers = {"Authorization": "Bearer " + client.token, "X-Ocean-Client": client.client_id,
               "Content-Type": "application/json"}
    if case == "origin":
        headers["Origin"] = "https://other.example"
    if case == "host":
        headers["Host"] = "other.example"
    if case == "chunked":
        headers["Transfer-Encoding"] = "chunked"
    connection = HTTPConnection("127.0.0.1", service.port, timeout=3)
    try:
        connection.request("POST", "/v1/focus/" + ("unknown" if case == "unknown" else "status"),
                           body=content, headers=headers)
        response = connection.getresponse()
        assert response.status in (400, 409)
        raw = response.read()
        assert json.loads(raw)["state"] == "HOLD" and client.token.encode() not in raw
        assert "Access-Control-Allow-Origin" not in response.headers
    finally:
        connection.close()
    assert h.starts == [] and make_client(h.operator).status()["waiting"] == []


def test_transport_stop_preserves_torch_and_restart_journal(transport):
    h, service, make_client = transport
    worker = make_client(h.compute)
    worker.submit(SlotRequest("compute", "compute", "slot", "focus-host", "key"))
    wait_for(lambda: worker.status()["state"] == "RUNNING")
    before = h.writer.unresolved()
    service.stop()
    wait_for(service._finished.is_set)
    assert h.writer.unresolved() == before and before is not None
    assert h.controller.status(*h.auth())["torch"]["request_id"] == "compute"


def test_invalid_client_config_json_and_foreign_service_pid_are_rejected(transport, monkeypatch):
    h, service, make_client = transport
    client = make_client(h.compute)
    for change in ({"port": False}, {"port": 65536}, {"token": "a\n" * 32},
                   {"timeout_seconds": float("nan")}, {"authority_id": ""}):
        with pytest.raises(ValueError):
            replace(client, **change)
    for raw in (b'{}x', b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b' ' * (LIMIT + 1)):
        with pytest.raises(ValueError):
            decode_json(raw)
    with monkeypatch.context() as context:
        context.setattr(os, "getpid", lambda: -1)
        with pytest.raises(Hold, match="foreign"):
            service.close()


def test_stop_fences_a_request_arriving_while_accept_loop_is_waiting(transport, monkeypatch):
    h, service, make_client = transport
    entered, accept = Event(), Event()
    original = service._server.handle_request
    def paused_accept():
        entered.set()
        assert accept.wait(3)
        original()
    monkeypatch.setattr(service._server, "handle_request", paused_accept)
    assert entered.wait(3)
    service.stop()
    client = make_client(h.compute)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.submit, SlotRequest("late-job", "compute", "slot", "focus-host", "late-key"))
            accept.set()
            with pytest.raises(Hold):
                future.result(timeout=5)
    finally:
        accept.set()
    assert h.controller.status(*h.auth())["waiting"] == [] and h.starts == []


def test_network_finish_waits_for_poll_without_blocking_status_or_new_requests(transport, monkeypatch):
    h, service, make_client = transport
    client = make_client(h.compute)
    client.submit(SlotRequest("compute", "compute", "slot", "focus-host", "key"))
    ready = wait_for(lambda: running(client, "compute"))
    entered, release, finish_called = Event(), Event(), Event()
    original_drive, original_finish = h.controller._drive, h.controller.finish
    def drive():
        if current_thread().name == "ocean-host-poll":
            entered.set()
            assert release.wait(5)
        return original_drive()
    def finish(*args):
        finish_called.set()
        return original_finish(*args)
    monkeypatch.setattr(h.controller, "_drive", drive)
    monkeypatch.setattr(h.controller, "finish", finish)
    assert entered.wait(3)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.finish, Grant(**ready["torch"]))
            assert not finish_called.wait(.15)
            assert client.status()["host_id"] == "focus-host"
            assert client.submit(SlotRequest("later", "media", "other", "focus-host", "later-key")) == "later"
            release.set()
            result = future.result(timeout=5)
            assert result["state"] == "RUNNING" and result["torch"]["request_id"] == "later"
            assert finish_called.is_set()
    finally:
        release.set()


def test_absolute_input_deadline_and_stop_close_unauthenticated_drips(transport):
    h, service, make_client = transport
    peers = []
    try:
        for _ in range(8):
            peer = socket.create_connection(("127.0.0.1", service.port), timeout=2)
            peer.sendall(b"POST /v1/focus/status HTTP/1.0\r\nX-Drip: ")
            peers.append(peer)
        wait_for(lambda: len(service._server._workers) == 8)
        started = time.monotonic()
        while time.monotonic() - started < 2.4:
            for peer in peers:
                try:
                    peer.sendall(b"a")
                except OSError:
                    pass
            time.sleep(.1)
        assert make_client(h.operator).status()["state"] == "IDLE"
        service.close()
        assert service._server._workers == set()
    finally:
        for peer in peers:
            peer.close()


def test_automatic_native_callback_can_read_same_service_and_poll_failure_holds(transport, monkeypatch):
    h, service, make_client = transport
    client = make_client(h.compute)
    original = h.adapter.start
    observed = []
    def start(*args):
        observed.append(client.status()["state"])
        return original(*args)
    # Replace the explicit fixture adapter before any execution is granted.
    monkeypatch.setattr(h.facade, "adapters", MappingProxyType({**h.facade.adapters,
                       "compute": replace(h.adapter, start=start)}))
    client.submit(SlotRequest("compute", "compute", "slot", "focus-host", "key"))
    wait_for(lambda: running(client, "compute"))
    assert observed == ["TRANSITION"]
    client.submit(SlotRequest("waiting", "media", "other", "focus-host", "waiting-key"))
    def fail(*args):
        raise RuntimeError("private failure detail must not reach a client")
    monkeypatch.setattr(h.controller, "tick", fail)
    wait_for(service._poll_failed.is_set)
    state = client.status()
    assert state["state"] == "HOLD" and "private failure" not in state["error"]
    with pytest.raises(Hold):
        client.submit(SlotRequest("later", "compute", "other", "focus-host", "later-key"))
    starts = len(h.starts)
    with pytest.raises(Hold):
        client.finish(Grant(**state["torch"]))
    assert len(h.starts) == starts and [request["request_id"] for request in state["waiting"]] == ["waiting"]
    assert h.writer.unresolved() is not None and state["torch"]["request_id"] == "compute"


def test_finish_waiting_behind_failed_poll_cannot_start_queued_work(transport, monkeypatch):
    h, service, make_client = transport
    client = make_client(h.compute)
    client.submit(SlotRequest("compute", "compute", "slot", "focus-host", "key"))
    ready = wait_for(lambda: running(client, "compute"))
    client.submit(SlotRequest("waiting", "media", "other", "focus-host", "waiting-key"))
    poll_entered, release, finish_waiting = Event(), Event(), Event()
    original = service._transition
    def fail(*args):
        poll_entered.set()
        assert release.wait(5)
        raise RuntimeError("expected isolated polling failure")
    def transition(operation, *args):
        if operation == "finish":
            finish_waiting.set()
        return original(operation, *args)
    monkeypatch.setattr(h.controller, "tick", fail)
    monkeypatch.setattr(service, "_transition", transition)
    assert poll_entered.wait(3)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.finish, Grant(**ready["torch"]))
            assert finish_waiting.wait(3)
            release.set()
            with pytest.raises(Hold):
                future.result(timeout=5)
    finally:
        release.set()
    state = client.status()
    assert state["state"] == "HOLD" and state["torch"]["request_id"] == "compute"
    assert [entry["request_id"] for entry in state["waiting"]] == ["waiting"] and len(h.starts) == 1
