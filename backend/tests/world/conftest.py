import pytest


@pytest.fixture(autouse=True)
def world_runtime_config(runtime_config):
    runtime_config.snapshots.ignored_paths = []
    triggers = runtime_config.self_check.event_triggers
    triggers.after_server_created = False
    triggers.after_server_populated = False
    triggers.after_world_restored = False
    triggers.after_world_rolled_back = False
    return runtime_config
