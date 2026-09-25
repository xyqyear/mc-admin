"""Explicit runtime binding for request, worker and command entrypoints."""

import asyncio
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime import Runtime

_active_runtime: ContextVar["Runtime | None"] = ContextVar("mc_admin_runtime", default=None)


def bound_runtime() -> "Runtime | None":
    return _active_runtime.get()


def current_runtime() -> "Runtime":
    runtime = bound_runtime()
    if runtime is None:
        raise RuntimeError("No application runtime is bound to this execution")
    return runtime


@contextmanager
def bind_runtime(runtime: "Runtime") -> Iterator[None]:
    token = _active_runtime.set(runtime)
    try:
        yield
    finally:
        _active_runtime.reset(token)


def spawn_background[T](coroutine: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
    return current_runtime().spawn(coroutine, name=name)
