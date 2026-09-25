from types import SimpleNamespace

import pytest

from app.dynamic_config.configs.world import WorldConfig
from tests.support.runtime import set_runtime_resource


@pytest.fixture(autouse=True)
def world_runtime_config(monkeypatch):
    runtime_config = SimpleNamespace(world=WorldConfig())
    set_runtime_resource(monkeypatch, 'dynamic_configuration', runtime_config)
