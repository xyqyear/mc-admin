"""Overrides of explicit resources in the current test's owned runtime."""

from typing import Any
from unittest.mock import DEFAULT, MagicMock

import pytest

from app.runtime_resources import current_runtime

_MISSING = object()


def set_runtime_resource(monkeypatch: pytest.MonkeyPatch, name: str, value: Any) -> None:
    monkeypatch.setitem(current_runtime().resources, name, value)


class patch_runtime_resource:
    def __init__(self, name: str, new: Any = DEFAULT, *, new_callable=None, **kwargs: Any) -> None:
        self.name = name
        self.new = new
        self.new_callable = new_callable or MagicMock
        self.kwargs = kwargs
        self.resources: dict[str, Any] | None = None
        self.original: Any = _MISSING

    def start(self) -> Any:
        if self.resources is not None:
            raise RuntimeError("Runtime resource override is already active")
        self.resources = current_runtime().resources
        self.original = self.resources.get(self.name, _MISSING)
        value = self.new_callable(**self.kwargs) if self.new is DEFAULT else self.new
        self.resources[self.name] = value
        return value

    def stop(self) -> None:
        if self.resources is None:
            return
        if self.original is _MISSING:
            self.resources.pop(self.name, None)
        else:
            self.resources[self.name] = self.original
        self.resources = None

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
