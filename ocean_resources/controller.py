"""Authenticated host focus policy over the existing arbiter and native ports.

No queue discovery, model loading, process signals or hidden polling thread.
An existing host loop explicitly calls tick(). Native executors own job state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from copy import deepcopy
import json
import os
import secrets
from threading import Lock, RLock

from .adapters import BACHFacade
from .contracts import Grant, Hold, Override, SlotRequest, identity, instant


@dataclass(frozen=True)
class FocusPolicy:
    idle_seconds: float = 30
    interactive_slice_seconds: float = 120
    background_min_seconds: float = 10

    def __post_init__(self):
        if any(not instant(v) or not 0 < v <= 3600 for v in asdict(self).values()):
            raise ValueError("focus durations must be positive, finite and at most one hour")


@dataclass(frozen=True)
class ControllerClient:
    client_id: str
    sockets: frozenset[str]
    token: str = field(repr=False, default_factory=lambda: secrets.token_urlsafe(32))
    operator: bool = False
    allow_interactive: bool = False
    priority_floor: int = 1

    def __post_init__(self):
        identity(self.client_id)
        if not isinstance(self.sockets, frozenset) or not self.sockets:
            raise ValueError("explicit immutable client socket scope required")
        for name in self.sockets:
            identity(name)
        if not isinstance(self.token, str) or not 32 <= len(self.token) <= 128 or not self.token.isascii():
            raise ValueError("bounded private ASCII client token required")
        if type(self.operator) is not bool or type(self.allow_interactive) is not bool:
            raise ValueError("explicit boolean client permissions required")
        if type(self.priority_floor) is not int or not 1 <= self.priority_floor <= 4:
            raise ValueError("client priority floor must be P1..P4")


@dataclass(frozen=True)
class OverrideCommand:
    command_id: str
    host_id: str
    authority_id: str
    request_id: str | None
    reason: str
    expires_at: float

    def __post_init__(self):
        for value in (self.command_id, self.host_id, self.authority_id):
            identity(value)
        # Clear commands still need a reason and bounded future lifetime.
        Override("clear" if self.request_id is None else self.request_id, self.reason, self.expires_at)


class ControllerAudit:
    """Fsynced local audit, under the same host writer; never contains tokens."""
    def __init__(self, authority):
        self.authority = authority
        self.path = authority.directory / (authority.host_id + ".focus-audit.jsonl")

    def __call__(self, event: dict):
        self.authority.require()
        path = self.path
        if path.is_symlink():
            raise Hold("linked focus audit refused")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "ab", buffering=0) as stream:
            opened = os.fstat(stream.fileno())
            current = path.stat(follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or opened.st_nlink != 1:
                raise Hold("focus audit identity changed")
            if opened.st_size >= 16 * 1024 * 1024:
                raise Hold("focus audit requires explicit archival")
            content = (json.dumps(event, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            if len(content) > 4096 or stream.write(content) != len(content):
                raise Hold("focus audit write failed")
            os.fsync(stream.fileno())


class HostController:
    """Single host-loop controller. Callbacks run outside its state mutex.

    Tokens authorize configured local clients, not arbitrary code in this Python
    process. Their private distribution and any transport remain application-owned.
    No caller-provided authentication boolean is accepted. Admission, budget,
    task claims, checkpoints and publish gates are never overridden here.
    """
    def __init__(self, facade: BACHFacade, clients: tuple[ControllerClient, ...],
                 policy: FocusPolicy = FocusPolicy(), *, audit=None):
        if not isinstance(facade, BACHFacade) or not isinstance(policy, FocusPolicy):
            raise ValueError("existing facade and focus policy required")
        if not isinstance(clients, tuple) or not clients or any(not isinstance(c, ControllerClient) for c in clients):
            raise ValueError("explicit immutable client configuration required")
        if len({c.client_id for c in clients}) != len(clients) or len({c.token for c in clients}) != len(clients):
            raise ValueError("client identities and credentials must be unique")
        if audit is not None and not callable(audit):
            raise ValueError("audit must be callable")
        self.facade, self.arbiter, self.policy = facade, facade.arbiter, policy
        self.arbiter.claim_controller()
        self._pid = os.getpid()
        self._authority_id = self.arbiter.authority.authority_id
        self._clients = {c.client_id: c for c in clients}
        self._owners: dict[str, str] = {}
        self._commands: dict[str, tuple[str, OverrideCommand]] = {}
        self._mutex, self._transition_lock = RLock(), Lock()
        self._active: Grant | None = None
        self._started = self._activity = self._protected_until = 0.0
        self._last_clock = self.arbiter.now()
        self._turns: set[str] = set()
        self._ended_turns: set[str] = set()
        self._return: tuple[str, bool] | None = None
        self._transition: dict | None = None
        self._error: str | None = None
        self._audit_fault = False
        self._audit_sink = ControllerAudit(self.arbiter.authority) if audit is None else audit

    def _authenticate(self, client_id, token) -> ControllerClient:
        # The PID fence precedes every potentially inherited lock.
        if os.getpid() != self._pid:
            raise Hold("foreign controller process")
        self.arbiter.authority.require()
        if self.arbiter.authority.authority_id != self._authority_id:
            raise Hold("controller writer session changed")
        client = self._clients.get(client_id) if isinstance(client_id, str) else None
        if client is None or not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(client.token, token):
            raise Hold("controller client authentication failed")
        return client

    def _now(self):
        value = self.arbiter.now()
        if value < self._last_clock:
            raise Hold("controller clock regressed")
        self._last_clock = value
        return value

    def _audit(self, event, **fields):
        value = {"schema": "ocean-host-focus-event.v1", "event": event,
                 "host_id": self.arbiter.authority.host_id, "authority_id": self._authority_id,
                 "at": self._now(), **fields}
        try:
            self._audit_sink(value)
        except Exception as exc:
            self._audit_fault = True
            raise Hold("controller audit unavailable") from exc

    def _owned(self, client, grant):
        if not isinstance(grant, Grant) or grant != self._active:
            raise Hold("stale or foreign controller grant")
        if not client.operator and self._owners.get(grant.request_id) != client.client_id:
            raise Hold("client does not own this request")
        return self.arbiter.request_for(grant)

    def submit(self, client_id: str, token: str, request: SlotRequest) -> str:
        client = self._authenticate(client_id, token)
        with self._mutex:
            if (not isinstance(request, SlotRequest) or request.socket_id not in client.sockets
                or request.priority < client.priority_floor or request.interactive and not client.allow_interactive):
                raise Hold("request exceeds configured client scope")
            old = self._owners.get(request.request_id)
            if old is not None and old != client.client_id:
                raise Hold("request belongs to another native client")
            if old is None:
                self._audit("submit-requested", client_id=client_id, request_id=request.request_id)
            result = self.arbiter.submit(request)
            self._owners[request.request_id] = client_id
            return result

    def begin_turn(self, client_id, token, grant: Grant, turn_id: str):
        client = self._authenticate(client_id, token)
        identity(turn_id)
        with self._mutex:
            request = self._owned(client, grant)
            self.arbiter.require_running(grant)
            if self._audit_fault:
                raise Hold("controller audit unavailable")
            if turn_id in self._turns:
                return  # Idempotent retry is not fresh user activity.
            if (not request.interactive or turn_id in self._ended_turns or len(self._turns) >= 1024
                or len(self._ended_turns) + len(self._turns) >= 4096):
                raise Hold("invalid or completed interactive turn")
            now = self._now()
            self._turns.add(turn_id)
            self._activity = now

    def end_turn(self, client_id, token, grant: Grant, turn_id: str):
        client = self._authenticate(client_id, token)
        with self._mutex:
            self._owned(client, grant)
            if turn_id in self._ended_turns:
                return
            if turn_id not in self._turns:
                raise Hold("unknown interactive turn")
            now = self._now()
            self._turns.remove(turn_id)
            self._ended_turns.add(turn_id)
            self._activity = now

    def override(self, client_id, token, command: OverrideCommand):
        client = self._authenticate(client_id, token)
        with self._mutex:
            if not client.operator or not isinstance(command, OverrideCommand):
                raise Hold("operator credential and bound override command required")
            if command.host_id != self.arbiter.authority.host_id or command.authority_id != self._authority_id:
                raise Hold("foreign override host or writer session")
            old = self._commands.get(command.command_id)
            if old is not None:
                if old != (client_id, command):
                    raise Hold("override command identity conflict")
                return  # Replay cannot renew or reapply a previously consumed command.
            now = self._now()
            status = self.arbiter.status()
            if not 0 < command.expires_at - now <= status["policy"]["max_override_seconds"]:
                raise Hold("override expiry must be bounded and future")
            if command.request_id is not None and command.request_id not in {r["request_id"] for r in status["waiting"]}:
                raise Hold("override must name an existing waiting request")
            if len(self._commands) >= 10000:
                raise Hold("override command history requires explicit archival")
            self._audit("override-requested", client_id=client_id, command=asdict(command))
            self.arbiter.set_override(None if command.request_id is None else Override(
                command.request_id, command.reason, command.expires_at))
            self._commands[command.command_id] = (client_id, command)

    def _snapshot(self):
        state = self.arbiter.status()
        error = self._error or ("controller audit unavailable" if self._audit_fault else None)
        if not self._transition and state["torch"] != (asdict(self._active) if self._active else None):
            # Never adopt a reservation, including one retained by a failed start.
            error = "unowned or failed-start torch; original execution reconciliation required"
        return {"schema": "ocean-host-controller.v1", "host_id": state["host_id"],
                "authority_id": self._authority_id, "state": "HOLD" if error else (
                    "TRANSITION" if self._transition else "RETURN_REQUESTED" if self._return else (
                        "RUNNING" if self._active else "IDLE")),
                "error": error, "torch": state["torch"], "waiting": state["waiting"],
                "override": state["override"], "in_flight_turns": len(self._turns),
                "return": self._return, "transition": deepcopy(self._transition),
                "policy": asdict(self.policy), "protected_until": self._protected_until,
                "profile_admission": "unchanged-default-closed", "native_job_state": "native-executor-owned"}

    def status(self, client_id, token):
        self._authenticate(client_id, token)
        with self._mutex:
            return self._snapshot()

    def tick(self, client_id, token):
        self._authenticate(client_id, token)
        if not self._transition_lock.acquire(blocking=False):
            return self.status(client_id, token)
        try:
            return self._drive()
        finally:
            self._transition_lock.release()

    def _drive(self):
        # At most one return and one start per poll; callbacks never hold _mutex.
        try:
            with self._mutex:
                now = self._now()
                state = self.arbiter.status()
                if state["torch"] != (asdict(self._active) if self._active else None):
                    raise Hold("unowned or failed-start torch; original execution reconciliation required")
                if self._audit_fault:
                    self._audit("audit-restored", active_grant=state["torch"])
                    self._audit_fault = False
                    self._error = None
                if self._active is not None:
                    request = self.arbiter.request_for(self._active)
                    waiting = bool(state["waiting"])
                    candidate = self.arbiter.next_request() if waiting else None
                    override = state["override"]
                    if self._return is None:
                        if state["heartbeat_expired"] or state["return_requested"]:
                            self._return = ("return-or-expired-heartbeat", not request.interactive)
                        elif override and override["expires_at"] > now:
                            self._return = ("operator-override", not request.interactive)
                        elif request.interactive and not self._turns and now - self._activity >= self.policy.idle_seconds:
                            self._return = ("chat-idle", False)
                        elif request.interactive and waiting and now - self._started >= self.policy.interactive_slice_seconds:
                            self._return = ("interactive-slice-ended", False)
                        elif (candidate and not request.interactive
                              and (candidate.priority < request.priority or candidate.interactive)
                              and (not candidate.interactive or now >= self._protected_until)):
                            self._return = ("higher-priority-request", True)
                    if self._return is None:
                        self.arbiter.heartbeat(self._active)
                        self._error = None
                        return self._snapshot()
                    if not state["return_requested"]:
                        self._audit("return-requested", reason=self._return[0], grant=asdict(self._active))
                        self.arbiter.request_return(self._active)
                    if self._turns:
                        return self._snapshot()
                    grant = self._active
                    requeue = self._return[1]
                    self._transition = {"action": "return", "token": secrets.token_hex(16), "grant": asdict(grant)}
                else:
                    grant = None
            if grant is not None:
                self.facade.yield_active(grant, requeue=requeue)
                with self._mutex:
                    if self._active != grant:
                        raise Hold("controller grant changed during handoff")
                    self._active, self._return, self._transition = None, None, None
                    self._turns.clear()
                    self._ended_turns.clear()
                    self._audit("released", grant=asdict(grant), requeued=requeue)
            with self._mutex:
                state = self.arbiter.status()
                if not state["waiting"]:
                    self._error = None
                    return self._snapshot()
                previous_burst = state["chat_burst_count"]
                burst_limit = state["policy"]["max_chat_burst"]
                self._audit("start-requested", candidate_request=self.arbiter.next_request().request_id)
                self._transition = {"action": "start", "token": secrets.token_hex(16)}
            started = self.facade.start_next()
            with self._mutex:
                self._active = started
                self._started = self._activity = self._now()
                request = self.arbiter.request_for(started)
                self._protected_until = (self._started + self.policy.background_min_seconds
                                         if not request.interactive and previous_burst >= burst_limit else self._started)
                self._transition = None
                self._error = None
                self._audit("started", grant=asdict(started))
                return self._snapshot()
        except Hold as exc:
            with self._mutex:
                self._transition = None
                self._error = str(exc)
                return self._snapshot()

    def finish(self, client_id, token, grant: Grant):
        client = self._authenticate(client_id, token)
        if not self._transition_lock.acquire(blocking=False):
            raise Hold("controller handoff is in progress")
        try:
            with self._mutex:
                self._owned(client, grant)
                if self._turns:
                    raise Hold("interactive turn still in flight")
                if self._return is not None and self._return[1] is not False:
                    raise Hold("existing handoff must retain its original requeue decision")
                if self._return is None:
                    self._return = ("native-owner-finished", False)
            return self._drive()
        finally:
            self._transition_lock.release()
