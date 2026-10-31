import pytest

from app.dynamic_config.configs.log_parser import LogParserConfig
from app.dynamic_config.manager import ConfigManager
from app.dynamic_config.migration import ConfigMigrator
from app.log_monitor.events import PlayerChatMessageEvent
from app.log_monitor.parser import LogParser


@pytest.mark.parametrize(
    "data",
    [
        {"chat_pattern": "["},
        {"chat_pattern": r"<(\S+)> (.*)"},
        {"uuid_patterns": [r"UUID (\S+)"]},
        {"join_pattern": "joined"},
        {"achievement_patterns": ["["]},
    ],
)
async def test_invalid_rule_update_preserves_current_config(data, db_session_factory):
    manager = ConfigManager(session_factory=db_session_factory)
    manager.register_config("log_parser", LogParserConfig)
    await manager.initialize_all_configs()
    await manager.update_config("log_parser", {"chat_pattern": r"^(CHAT )?(\S+): (.*)$"})
    current = manager.get_config("log_parser").model_dump()
    with pytest.raises(ValueError, match="日志规则"):
        await manager.update_config("log_parser", data)
    assert manager.get_config("log_parser").model_dump() == current
    reloaded = ConfigManager(session_factory=db_session_factory)
    reloaded.register_config("log_parser", LogParserConfig)
    await reloaded.initialize_all_configs()
    assert reloaded.get_config("log_parser").model_dump() == current


async def test_valid_rule_extracts_chat_and_preserves_legacy_loading(runtime_config, isolated_runtime):
    await isolated_runtime.config_manager.update_config(
        "log_parser", {"chat_pattern": r"^(E2E: )?<(\S+)> (.*)$"},
    )
    event = LogParser().parse_line("server", "E2E: <Alex> hello")
    assert isinstance(event, PlayerChatMessageEvent)
    assert event.player_name == "Alex"
    assert event.message == "hello"
    legacy = LogParserConfig.model_validate({"chat_pattern": "["})
    assert legacy.chat_pattern == "["


def test_default_rules_satisfy_update_contract():
    LogParserConfig.model_validate({}).validate_update()


@pytest.mark.parametrize(
    "leave_pattern",
    [
        pytest.param(r"^(?!.*<).* (\S+) lost connection: (.*)", id="old-default"),
        pytest.param(r"^LEAVE (\S+) :: (.*)$", id="custom"),
    ],
)
def test_saved_leave_rule_survives_schema_change(leave_pattern):
    stored = {"leave_pattern": leave_pattern, "join_pattern": r"^JOIN (\S+)$"}

    migrated, _ = ConfigMigrator.migrate_config(stored, LogParserConfig, "previous-schema")

    assert migrated["leave_pattern"] == leave_pattern
    assert migrated["join_pattern"] == stored["join_pattern"]


@pytest.mark.parametrize(
    "stored_rules",
    [
        pytest.param(
            {
                "join_pattern": r"^(?!.*<).* (\S+)\[/.*?\] logged in with entity",
                "chat_pattern": r": (\[Not Secure\] )?<(\S+)> (.*)",
                "achievement_patterns": [
                    r"^(?!.*<).*\]: (.+) has made the advancement \[(.*)\]",
                    r"^(?!.*<).* (\S+) has just earned the achievement \[(.*)\]",
                ],
                "server_stop_pattern": r"^(?!.*<).*Stopping server",
            },
            id="old-defaults",
        ),
        pytest.param(
            {
                "join_pattern": r"^JOIN (\S+)$",
                "chat_pattern": r"^(CUSTOM )?(\S+): (.*)$",
                "achievement_patterns": [r"^ACH (\S+): (.*)$"],
                "server_stop_pattern": r"^STOP$",
            },
            id="custom",
        ),
    ],
)
def test_saved_scalar_and_list_rules_survive_schema_change(stored_rules):
    stored = {**LogParserConfig.model_validate({}).model_dump(), **stored_rules}

    migrated, _ = ConfigMigrator.migrate_config(stored, LogParserConfig, "previous-schema")

    assert migrated == stored
