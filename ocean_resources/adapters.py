"""Injected hybrid/BACH ports; never import a live BACH runtime or discover jobs."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import RLock
from types import MappingProxyType
from typing import Callable
import uuid

from .arbiter import HostLocalArbiter
from .contracts import Checkpoint, ExitReadback, Grant, Hold, HybridPlannerPointer, SlotRequest, identity


@dataclass(frozen=True)
class ComputeExecutorAdapter:
    """Application owns checkpoint persistence, process identity and exit/RAM probes.

    Callbacks must be profiled and authorized separately before any live use.
    Admission requires explicit fixture or independently reviewed native profiles. No queue import/write
    and no signal/OS/model command is implemented by this adapter.
    """
    start: Callable[[Grant, SlotRequest, Checkpoint | None, str], bool]
    checkpoint: Callable[[Grant, str], Checkpoint]
    stop: Callable[[Grant, str, Checkpoint], None]
    readback: Callable[[Grant, str], ExitReadback]
    workload_sha256: str | None = None
    execution_kind: str | None = None


@dataclass(frozen=True)
class ModelSocketBinding:
    """Preserves HostInferenceGate's exact five model_target fields."""
    socket_id: str
    binding_id: str
    agent_id: str
    backend: str
    model: str

    def __post_init__(self):
        for value in (self.socket_id, self.binding_id, self.agent_id, self.backend, self.model):
            if not isinstance(value, str) or not value or len(value) > 192:
                raise ValueError("invalid existing model binding")

    def target(self) -> dict:
        return {
            "socket_id": self.socket_id, "binding_id": self.binding_id,
            "agent_id": self.agent_id, "backend": self.backend, "model": self.model,
        }


class ModelSocketInferenceAdapter:
    """Wraps the existing async gate.turn contract, without renaming it."""
    def __init__(self, arbiter: HostLocalArbiter, binding: ModelSocketBinding, gate):
        self._arbiter, self.binding, self._gate = arbiter, binding, gate

    @asynccontextmanager
    async def turn(self, grant: Grant, chat_id: str):
        request = self._arbiter.request_for(grant)
        if grant.socket_id != self.binding.socket_id:
            raise Hold("model binding belongs to another resource socket")
        # A CPU process measurement cannot authorize an external model daemon.
        self._arbiter.require_workload(grant, None, kind="model-api")
        self._arbiter.require_running(grant)
        async with self._gate.turn(
            chat_id,
            "foreground" if request.interactive else "background",
            check_ready=lambda: self._arbiter.require_running(grant),
            model_target=self.binding.target(),
        ):
            self._arbiter.require_running(grant)
            yield


class BACHFacade:
    """In-memory facade. No DB import, BACH boot or task/queue claim is implied."""
    def __init__(self, arbiter: HostLocalArbiter, adapters: dict[str, ComputeExecutorAdapter]):
        self.arbiter = arbiter
        self.adapters = MappingProxyType(dict(adapters))
        self._executions: dict[Grant, tuple[ComputeExecutorAdapter, str]] = {}
        self._mutex = RLock()

    @staticmethod
    def request_from_pipeline(job: dict, catalog: dict, *, socket_id: str, slot_id: str) -> SlotRequest:
        """General pipeline port; does not require or invent a model binding."""
        from .pipelines import slot_request
        return slot_request(job, catalog, socket_id=socket_id, slot_id=slot_id)

    @staticmethod
    def request_from_task(
        task: dict, binding: ModelSocketBinding, pointer: HybridPlannerPointer,
        *, host_id: str, request_id: str, idempotency_key: str,
    ) -> SlotRequest:
        # Preserve the existing required_model and assigned_slot; do not replace
        # them with a resource socket or claim a legacy task-schema migration.
        if task.get("required_model") != binding.model:
            raise Hold("task required_model does not match the existing binding")
        slot = task.get("assigned_slot")
        if not isinstance(slot, str):
            raise Hold("task assigned_slot is unknown")
        identity(slot)
        task_id = task.get("id")
        if type(task_id) is not int or task_id <= 0 or str(task_id) != pointer.task_id:
            raise Hold("planner pointer does not identify the original task")
        priority = task.get("priority")
        if isinstance(priority, str) and priority in {"P1", "P2", "P3", "P4"}:
            priority = int(priority[1])
        return SlotRequest(
            request_id, binding.socket_id, slot, host_id, idempotency_key,
            priority=priority, pointer=pointer,
        )

    def start_next(self) -> Grant:
        with self._mutex:
            grant = self.arbiter.acquire()
            adapter = self.adapters.get(grant.socket_id)
            if not isinstance(adapter, ComputeExecutorAdapter):
                raise Hold("missing executor adapter; reservation remains held")
            self.arbiter.require_workload(grant, adapter.workload_sha256, kind=adapter.execution_kind)
            execution_id = uuid.uuid4().hex
            self.arbiter.bind_execution(grant, execution_id)
            self._executions[grant] = (adapter, execution_id)
            try:
                result = adapter.start(
                    grant, self.arbiter.request_for(grant),
                    self.arbiter.checkpoint_for(grant.request_id), execution_id,
                )
            except Exception as exc:
                raise Hold("executor start failed; reservation remains held") from exc
            if result is not True:
                raise Hold("executor start is unverified; reservation remains held")
            return grant

    def yield_active(self, grant: Grant, *, requeue: bool = True) -> Checkpoint:
        with self._mutex:
            self.arbiter.request_for(grant)
            if grant not in self._executions:
                raise Hold("unknown execution identity")
            adapter, execution_id = self._executions[grant]
            self.arbiter.request_return(grant)
            try:
                checkpoint = adapter.checkpoint(grant, execution_id)
                if not isinstance(checkpoint, Checkpoint) or not checkpoint.valid_for(grant):
                    raise Hold("checkpoint invalid; executor will not be stopped")
                adapter.stop(grant, execution_id, checkpoint)
                exit_readback = adapter.readback(grant, execution_id)
                self.arbiter.release(grant, checkpoint, exit_readback, requeue=requeue)
            except Hold:
                raise
            except Exception as exc:
                raise Hold("handoff failed; reservation remains held") from exc
            del self._executions[grant]
            return checkpoint
