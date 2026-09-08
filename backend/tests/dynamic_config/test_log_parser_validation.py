from unittest.mock import AsyncMock, patch

import pytest

from app.dynamic_config.configs.log_parser import LogParserConfig
from app.dynamic_config.manager import ConfigManager
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
async def test_invalid_rule_update_preserves_current_config(data):
    manager = ConfigManager()
    manager.register_config("log_parser", LogParserConfig)
    current = LogParserConfig.model_validate({})
    manager._configs["log_parser"] = current
    manager._initialized = True
    with patch("app.dynamic_config.manager.crud.upsert_config", new_callable=AsyncMock) as save:
        with pytest.raises(ValueError, match="日志规则"):
            await manager.update_config("log_parser", data)
        save.assert_not_called()
    assert manager.get_config("log_parser") is current


def test_valid_rule_extracts_chat_and_preserves_legacy_loading():
    rule = LogParserConfig.model_validate({"chat_pattern": r"^(E2E: )?<(\S+)> (.*)$"})
    rule.validate_update()
    with patch("app.log_monitor.parser.config") as config:
        config.log_parser = rule
        event = LogParser().parse_line("server", "E2E: <Alex> hello")
    assert isinstance(event, PlayerChatMessageEvent)
    assert event.player_name == "Alex"
    assert event.message == "hello"
    legacy = LogParserConfig.model_validate({"chat_pattern": "["})
    assert legacy.chat_pattern == "["


def test_default_rules_satisfy_update_contract():
    LogParserConfig.model_validate({}).validate_update()
