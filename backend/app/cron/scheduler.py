"""Schedule callbacks independently of the operation changing a schedule."""

from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..runtime_resources import runtime_context

if TYPE_CHECKING:
    from ..runtime import Runtime


class RuntimeAsyncIOScheduler(AsyncIOScheduler):
    def __init__(self, runtime: "Runtime") -> None:
        super().__init__()
        self._runtime = runtime

    def wakeup(self) -> None:
        # APScheduler copies this context into both its immediate callback and next timer.
        runtime_context(self._runtime).run(super().wakeup)
