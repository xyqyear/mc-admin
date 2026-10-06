"""Overrides of explicit resources in the current test's owned runtime."""

from typing import Any
from unittest.mock import DEFAULT, MagicMock

import pytest

from app.runtime import Runtime
from app.runtime_resources import current_runtime


def replace_runtime_resource(runtime: Runtime, name: str, value: Any) -> None:
    field = name if name in {"settings", "operation_recovery", "world_restore_stages"} else f"_{name}"
    getattr(runtime, field)
    setattr(runtime, field, value)


def set_runtime_resource(monkeypatch: pytest.MonkeyPatch, name: str, value: Any) -> None:
    field = name if name in {"settings", "operation_recovery", "world_restore_stages"} else f"_{name}"
    monkeypatch.setattr(current_runtime(), field, value)


class patch_runtime_resource:
    def __init__(self, name: str, new: Any = DEFAULT, *, new_callable=None, **kwargs: Any) -> None:
        self.name = name
        self.new = new
        self.new_callable = new_callable or MagicMock
        self.kwargs = kwargs
        self.runtime: Runtime | None = None
        self.field = name if name in {"settings", "operation_recovery", "world_restore_stages"} else f"_{name}"
        self.original: Any = None

    def start(self) -> Any:
        if self.runtime is not None:
            raise RuntimeError("Runtime resource override is already active")
        self.runtime = current_runtime()
        self.original = getattr(self.runtime, self.field)
        value = self.new_callable(**self.kwargs) if self.new is DEFAULT else self.new
        setattr(self.runtime, self.field, value)
        return value

    def stop(self) -> None:
        if self.runtime is None:
            return
        setattr(self.runtime, self.field, self.original)
        self.runtime = None

    __enter__ = start

    def __exit__(self, *args: object) -> None:
        self.stop()


from collections.abc import Iterator
from contextlib import contextmanager

from app.config import Settings


@contextmanager
def patch_settings() -> Iterator[Settings]:
    settings = current_runtime().settings
    original = settings.model_copy(deep=True)
    try:
        yield settings
    finally:
        for name in Settings.model_fields:
            setattr(settings, name, getattr(original, name))
