from types import SimpleNamespace

import pytest

from app.dynamic_config.configs.mcmap import MCMapConfig
from app.dynamic_config.configs.self_check import (
    SelfCheckConfig,
    SelfCheckEventTriggerConfig,
)
from app.dynamic_config.configs.snapshots import WorldRestoreConfig
from app.dynamic_config.configs.world import WorldConfig
from tests.support.runtime import set_runtime_resource


@pytest.fixture(autouse=True)
def world_runtime_config(monkeypatch, isolated_runtime):
    runtime_config = SimpleNamespace(
        world=WorldConfig(),
        mcmap=MCMapConfig(),
        self_check=SelfCheckConfig(event_triggers=SelfCheckEventTriggerConfig(
            after_server_created=False,
            after_server_populated=False,
            after_world_restored=False,
            after_world_rolled_back=False,
        )),
        snapshots=SimpleNamespace(
            world_restore=WorldRestoreConfig(),
            ignored_paths=[],
        ),
    )
    set_runtime_resource(monkeypatch, 'dynamic_configuration', runtime_config)
