"""Native process client: fixed loopback, no proxy, redirects or credential output."""
from dataclasses import asdict, dataclass, field
from http.client import HTTPConnection
import json

from .contracts import Hold, identity
from .service import LIMIT, OPERATIONS, SCHEMA, decode_json


@dataclass(frozen=True)
class HostClient:
    port: int
    host_id: str
    authority_id: str
    client_id: str
    token: str = field(repr=False)
    timeout_seconds: float = 10

    def __post_init__(self):
        for value in (self.host_id, self.authority_id, self.client_id):
            identity(value)
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("explicit loopback port required")
        if (not isinstance(self.token, str) or not 32 <= len(self.token) <= 128
            or not self.token.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in self.token)):
            raise ValueError("private bounded ASCII client token required")
        if type(self.timeout_seconds) not in (int, float) or not .1 <= self.timeout_seconds <= 30:
            raise ValueError("bounded host client timeout required")

    def call(self, operation: str, payload: dict | None = None):
        if operation not in OPERATIONS or payload is not None and not isinstance(payload, dict):
            raise ValueError("explicit supported host operation and payload required")
        content = json.dumps({"schema": SCHEMA, "host_id": self.host_id, "authority_id": self.authority_id,
                              "payload": {} if payload is None else payload}, allow_nan=False).encode()
        if len(content) > LIMIT:
            raise ValueError("host client message exceeds bound")
        connection = HTTPConnection("127.0.0.1", self.port, timeout=self.timeout_seconds)
        try:
            connection.request("POST", "/v1/focus/" + operation, body=content,
                headers={"Authorization": "Bearer " + self.token, "X-Ocean-Client": self.client_id,
                         "Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(LIMIT + 1)
            result = decode_json(raw)
            if (response.status != 200 or response.getheader("Content-Type") != "application/json"
                or result.get("schema") != SCHEMA or result.get("state") != "OK"
                or set(result) != {"schema", "state", "result"}):
                raise Hold("host controller operation held or unavailable")
            return result["result"]
        except Exception as exc:
            raise Hold("host controller operation held or unavailable") from exc
        finally:
            connection.close()

    def submit(self, request):
        return self.call("submit", asdict(request))

    def status(self):
        return self.call("status")

    def begin_turn(self, grant, turn_id):
        return self.call("begin_turn", {"grant": asdict(grant), "turn_id": turn_id})

    def end_turn(self, grant, turn_id):
        return self.call("end_turn", {"grant": asdict(grant), "turn_id": turn_id})

    def finish(self, grant):
        return self.call("finish", {"grant": asdict(grant)})

    def override(self, command):
        return self.call("override", asdict(command))
