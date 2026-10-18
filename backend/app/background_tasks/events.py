import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.operations.changes import OperationChangeFeed

from .api_models import (
    BackgroundTaskEventResponse,
    OperationChangesEvent,
    PruneStateEvent,
    RestorationIndexEvent,
    TaskRemoveEvent,
    TaskSnapshotEvent,
    TaskUpsertEvent,
)
from .models import BackgroundTask

MAX_PENDING_TASKS = 256
HEARTBEAT_SECONDS = 15.0
ObservationDomain = Literal["restorations", "prune"]
ObservationIndex = Callable[[ObservationDomain], Awaitable[list[dict[str, Any]]]]
OBSERVATION_DOMAINS: tuple[ObservationDomain, ...] = ("restorations", "prune")


@dataclass(eq=False)
class TaskSubscription:
    pending: dict[str, None] = field(default_factory=dict)
    domains: set[ObservationDomain] = field(default_factory=set)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    snapshot_required: bool = True
    operations_dirty: bool = True
    closed: bool = False
    unlisten: Callable[[], None] | None = None

    def notify(self, task_id: str) -> None:
        if self.closed or self.snapshot_required:
            return
        self.pending[task_id] = None
        if len(self.pending) > MAX_PENDING_TASKS:
            self.pending.clear()
            self.snapshot_required = True
        self.ready.set()

    def notify_operation(self) -> None:
        self.operations_dirty = True
        self.ready.set()

    def notify_domain(self, domain: ObservationDomain) -> None:
        if not self.closed:
            self.domains.add(domain)
            self.ready.set()

    def close(self) -> None:
        self.closed = True
        self.pending.clear()
        self.domains.clear()
        if self.unlisten is not None:
            self.unlisten()
            self.unlisten = None
        self.ready.set()


class TaskEventStream:
    def __init__(
        self,
        get_task: Callable[[str], BackgroundTask | None],
        get_tasks: Callable[[], list[BackgroundTask]],
    ) -> None:
        self._get_task = get_task
        self._get_tasks = get_tasks
        self._subscriptions: set[TaskSubscription] = set()
        self._closed = False

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)

    def publish(self, task_id: str) -> None:
        for subscription in self._subscriptions:
            subscription.notify(task_id)

    def notify_observation(self, domain: ObservationDomain) -> None:
        for subscription in self._subscriptions:
            subscription.notify_domain(domain)

    def close(self) -> None:
        self._closed = True
        for subscription in self._subscriptions:
            subscription.close()
        self._subscriptions.clear()

    async def events(
        self,
        operation_cursor: str | None = None,
        get_index: ObservationIndex | None = None,
        changes: OperationChangeFeed | None = None,
    ) -> AsyncGenerator[bytes]:
        if self._closed:
            return
        subscription = TaskSubscription()
        self._subscriptions.add(subscription)
        subscription.unlisten = changes.listen(subscription.notify_operation) if changes is not None else None
        operations_initial = True

        async def index(domain: ObservationDomain) -> list[dict[str, Any]]:
            return await get_index(domain) if get_index is not None else []

        try:
            while not subscription.closed:
                emitted = False
                if subscription.snapshot_required:
                    subscription.snapshot_required = False
                    subscription.pending.clear()
                    subscription.domains.clear()
                    active_restorations = await index("restorations")
                    prune_states = await index("prune")
                    if subscription.closed:
                        return
                    event = TaskSnapshotEvent(
                        tasks=[BackgroundTaskEventResponse.from_task(task) for task in self._get_tasks()],
                        active_restorations=active_restorations, prune_states=prune_states,
                    )
                    yield b"data: " + event.model_dump_json().encode() + b"\n\n"
                    emitted = True
                if subscription.closed:
                    return
                if changes is not None and subscription.operations_dirty:
                    subscription.operations_dirty = False
                    batch = changes.read(operation_cursor)
                    operation_cursor = batch.next_cursor
                    # A pinned final page can have newer commits beyond its batch head.
                    subscription.operations_dirty |= batch.has_more or bool(batch.items)
                    if operations_initial or batch.items or batch.reset_required:
                        event = OperationChangesEvent(changes=batch)
                        yield b"data: " + event.model_dump_json().encode() + b"\n\n"
                        emitted = True
                    operations_initial = False
                for domain in OBSERVATION_DOMAINS:
                    if subscription.closed:
                        return
                    if domain not in subscription.domains:
                        continue
                    subscription.domains.remove(domain)
                    values = await index(domain)
                    if subscription.closed:
                        return
                    event = (
                        RestorationIndexEvent(active_restorations=values)
                        if domain == "restorations" else PruneStateEvent(prune_states=values)
                    )
                    yield b"data: " + event.model_dump_json().encode() + b"\n\n"
                    emitted = True
                if subscription.closed:
                    return
                if subscription.pending:
                    task_id = next(iter(subscription.pending))
                    del subscription.pending[task_id]
                    task = self._get_task(task_id)
                    event = (
                        TaskUpsertEvent(task=BackgroundTaskEventResponse.from_task(task))
                        if task is not None else TaskRemoveEvent(task_id=task_id)
                    )
                    yield b"data: " + event.model_dump_json().encode() + b"\n\n"
                    emitted = True
                if emitted:
                    await asyncio.sleep(0)
                    continue
                subscription.ready.clear()
                try:
                    await asyncio.wait_for(subscription.ready.wait(), HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield b": keepalive\n\n"
        finally:
            subscription.close()
            self._subscriptions.discard(subscription)
