from types import SimpleNamespace

import pytest

from app.dynamic_config.configs.world import WorldConfig


@pytest.fixture(autouse=True)
def world_runtime_config(monkeypatch):
    runtime_config = SimpleNamespace(world=WorldConfig())
    monkeypatch.setattr("app.world.dimension_labels.config", runtime_config)
    monkeypatch.setattr("app.world.layout.config", runtime_config)
