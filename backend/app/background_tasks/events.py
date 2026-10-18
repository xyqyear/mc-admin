import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field

from .api_models import (
    BackgroundTaskSummaryResponse,
    TaskRemoveEvent,
    TaskSnapshotEvent,
    TaskUpsertEvent,
)
from .models import BackgroundTask

MAX_PENDING_TASKS = 256
HEARTBEAT_SECONDS = 15.0


@dataclass(eq=False)
class TaskSubscription:
    pending: dict[str, None] = field(default_factory=dict)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    snapshot_required: bool = True
    closed: bool = False

    def notify(self, task_id: str) -> None:
        if self.closed or self.snapshot_required:
            return
        self.pending[task_id] = None
        if len(self.pending) > MAX_PENDING_TASKS:
            self.pending.clear()
            self.snapshot_required = True
        self.ready.set()

    def close(self) -> None:
        self.closed = True
        self.pending.clear()
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

    def close(self) -> None:
        self._closed = True
        for subscription in self._subscriptions:
            subscription.close()
        self._subscriptions.clear()

    async def events(self) -> AsyncGenerator[bytes]:
        if self._closed:
            return
        subscription = TaskSubscription()
        self._subscriptions.add(subscription)
        try:
            while not subscription.closed:
                if subscription.snapshot_required:
                    subscription.snapshot_required = False
                    subscription.pending.clear()
                    event = TaskSnapshotEvent(tasks=[
                        BackgroundTaskSummaryResponse.from_task(task)
                        for task in self._get_tasks()
                    ])
                elif subscription.pending:
                    task_id = next(iter(subscription.pending))
                    del subscription.pending[task_id]
                    task = self._get_task(task_id)
                    event = (
                        TaskUpsertEvent(task=BackgroundTaskSummaryResponse.from_task(task))
                        if task is not None else TaskRemoveEvent(task_id=task_id)
                    )
                else:
                    subscription.ready.clear()
                    try:
                        await asyncio.wait_for(subscription.ready.wait(), HEARTBEAT_SECONDS)
                    except TimeoutError:
                        yield b": keepalive\n\n"
                    continue
                yield b"data: " + event.model_dump_json().encode() + b"\n\n"
                await asyncio.sleep(0)
        finally:
            self._subscriptions.discard(subscription)
