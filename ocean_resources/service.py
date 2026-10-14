"""Explicit loopback transport for one existing host controller, never a job queue."""
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from threading import BoundedSemaphore, Event, Lock, Thread, current_thread
import time

from .contracts import Grant, Hold, HybridPlannerPointer, SlotRequest, identity, positive
from .controller import ControllerClient, HostController, OverrideCommand

SCHEMA = "ocean-host-transport.v1"
LIMIT = 1024 * 1024
OPERATIONS = frozenset({"status", "submit", "begin_turn", "end_turn", "override", "finish", "tick"})


def decode_json(raw: bytes) -> dict:
    if len(raw) > LIMIT:
        raise ValueError("transport message exceeds bound")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate transport field")
            result[key] = value
        return result
    def reject(value):
        raise ValueError("nonfinite transport value")
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("transport object required")
    return value


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("exact transport fields required")


def contract(cls, value):
    exact(value, (field.name for field in fields(cls)))
    if cls is SlotRequest and value["pointer"] is not None:
        value = {**value, "pointer": contract(HybridPlannerPointer, value["pointer"])}
    if cls is Grant:
        if not positive(value["generation"]):
            raise ValueError("positive grant generation required")
        for key in ("authority_id", "request_id", "socket_id", "slot_id"):
            identity(value[key])
    return cls(**value)


class _Server(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 8

    def __init__(self, address, handler):
        self._slots, self._mutex, self._workers = BoundedSemaphore(8), Lock(), set()
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        def serve():
            try:
                request.settimeout(2)
                self.finish_request(request, address)
            except Exception:
                pass  # Never log headers, credentials or arbitrary request bodies.
            finally:
                self.shutdown_request(request)
                with self._mutex:
                    self._workers.discard(current_thread())
                self._slots.release()
        worker = Thread(target=serve, name="ocean-host-request", daemon=False)
        with self._mutex:
            self._workers.add(worker)
        try:
            worker.start()
        except BaseException:
            with self._mutex:
                self._workers.discard(worker)
            self._slots.release()
            self.shutdown_request(request)
            raise

    def drain(self, seconds=5):
        deadline = time.monotonic() + seconds
        with self._mutex:
            workers = tuple(self._workers)
        for worker in workers:
            if worker is current_thread():
                raise Hold("host transport cannot close from its own request")
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in workers):
            raise Hold("host transport requests remain active; retain the host writer")


class HostService:
    """Caller-owned host loop with explicit startup and bounded local HTTP workers.

    The caller retains writer, controller and native executor lifetime. Stopping
    this transport never releases a torch, terminates a job, or clears a journal.
    There is no default port, global discovery, credential store or autostart.
    """
    def __init__(self, controller: HostController, operator: ControllerClient, *, port=0, tick_seconds=.25):
        if not isinstance(controller, HostController) or not isinstance(operator, ControllerClient):
            raise ValueError("existing controller and configured operator required")
        authenticated = controller._authenticate(operator.client_id, operator.token)
        if not authenticated.operator:
            raise Hold("host service polling requires an operator credential")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("explicit loopback port required")
        if type(tick_seconds) not in (int, float) or not .05 <= tick_seconds <= 1:
            raise ValueError("host polling interval must be .05..1 seconds")
        self.controller, self._operator = controller, operator
        self._pid, self._stop, self._running = os.getpid(), Event(), Lock()
        self._finished = Event()
        self._finished.set()
        self._closed = False
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            def log_message(self, *args):
                pass
            def send_error(self, code, message=None, explain=None):
                self.respond(400, {"schema": SCHEMA, "state": "HOLD"})
            def respond(self, code, data):
                content = json.dumps(data, sort_keys=True, allow_nan=False).encode()
                if len(content) > LIMIT:
                    code, content = 503, b'{"schema":"ocean-host-transport.v1","state":"HOLD"}'
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(content)
            def do_POST(self):
                try:
                    owner._require()
                    expected_host = f"127.0.0.1:{owner.port}"
                    if (self.headers.get_all("Host") != [expected_host] or self.headers.get_all("Origin")
                        or self.headers.get_all("Transfer-Encoding")
                        or len(self.headers.get_all("Authorization", [])) != 1
                        or len(self.headers.get_all("X-Ocean-Client", [])) != 1
                        or len(self.headers.get_all("Content-Length", [])) != 1
                        or self.headers.get("Content-Type") != "application/json"):
                        raise ValueError("invalid local transport headers")
                    authorization = self.headers["Authorization"]
                    if not authorization.startswith("Bearer "):
                        raise Hold("missing transport authentication")
                    client_id, token = self.headers["X-Ocean-Client"], authorization[7:]
                    owner.controller._authenticate(client_id, token)
                    length = int(self.headers["Content-Length"])
                    if not 0 < length <= LIMIT:
                        raise ValueError("bounded transport content length required")
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError("incomplete transport body")
                    message = decode_json(raw)
                    result = owner.dispatch(client_id, token, self.path, message)
                    self.respond(200, {"schema": SCHEMA, "state": "OK", "result": result})
                except Hold:
                    self.respond(409, {"schema": SCHEMA, "state": "HOLD"})
                except Exception:
                    self.respond(400, {"schema": SCHEMA, "state": "HOLD"})
        self._server = _Server(("127.0.0.1", port), Handler)
        self._server.timeout = tick_seconds
        self.port = self._server.server_address[1]

    def _require(self):
        if os.getpid() != self._pid or self._closed:
            raise Hold("foreign or closed host transport")
        self.controller.arbiter.authority.require()

    def dispatch(self, client_id, token, path, message):
        self._require()
        client = self.controller._authenticate(client_id, token)
        exact(message, ("schema", "host_id", "authority_id", "payload"))
        state = self.controller.status(client_id, token)
        if (message["schema"] != SCHEMA or message["host_id"] != state["host_id"]
            or message["authority_id"] != state["authority_id"]):
            raise Hold("transport targets a different host writer session")
        if not isinstance(path, str) or not path.startswith("/v1/focus/"):
            raise ValueError("unknown transport path")
        operation = path[len("/v1/focus/"):]
        if operation not in OPERATIONS:
            raise ValueError("unknown transport operation")
        payload = message["payload"]
        if operation in {"status", "tick"}:
            exact(payload, ())
            if operation == "tick" and not client.operator:
                raise Hold("operator polling permission required")
            return getattr(self.controller, operation)(client_id, token)
        if operation == "submit":
            return self.controller.submit(client_id, token, contract(SlotRequest, payload))
        if operation == "override":
            return self.controller.override(client_id, token, contract(OverrideCommand, payload))
        exact(payload, ("grant",) if operation == "finish" else ("grant", "turn_id"))
        grant = contract(Grant, payload["grant"])
        if operation == "finish":
            return self.controller.finish(client_id, token, grant)
        identity(payload["turn_id"])
        return getattr(self.controller, operation)(client_id, token, grant, payload["turn_id"])

    def serve_forever(self):
        self._require()
        if not self._running.acquire(blocking=False):
            raise Hold("host transport loop is already running")
        self._finished.clear()
        try:
            while not self._stop.is_set():
                self._require()
                self._server.handle_request()
                if not self._stop.is_set():
                    self.controller.tick(self._operator.client_id, self._operator.token)
        finally:
            self._finished.set()
            self._running.release()

    def stop(self):
        if os.getpid() != self._pid:
            raise Hold("foreign host transport process")
        self._stop.set()

    def close(self):
        self.stop()
        if not self._finished.wait(5):
            raise Hold("host transport loop remains active; retain the host writer")
        self._server.server_close()
        self._server.drain()
        self._closed = True
