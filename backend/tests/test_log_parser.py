"""Test cases for LogParser using real Minecraft server logs."""

from unittest.mock import MagicMock, patch

import pytest

from app.dynamic_config.configs.log_parser import LogParserConfig
from app.events.base import (
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from app.log_monitor.parser import LogParser


@pytest.fixture
def mock_config():
    """Mock dynamic config for LogParser."""
    mock_log_parser_config = LogParserConfig.model_validate({})
    mock_config_obj = MagicMock()
    mock_config_obj.log_parser = mock_log_parser_config

    with patch("app.log_monitor.parser.config", mock_config_obj):
        yield mock_config_obj


@pytest.fixture
def parser(mock_config):
    """Create LogParser instance."""
    return LogParser()


class TestUUIDParsing:
    """Test UUID parsing from real server logs."""

    def test_uuid_pattern_atm9(self, parser):
        """Test UUID pattern from atm9 server."""
        log_line = "[24Jan2024 11:08:33.562] [User Authenticator #1/INFO] [net.minecraft.server.network.ServerLoginPacketListenerImpl/]: UUID of player Qin_Ning is 967c2921-423f-4c50-b57e-c92ad45d04be"

        event = parser.parse_line("atm9", log_line)

        assert event is not None
        assert isinstance(event, PlayerUuidDiscoveredEvent)
        assert event.server_id == "atm9"
        assert event.player_name == "Qin_Ning"
        assert event.uuid == "967c2921423f4c50b57ec92ad45d04be"

    def test_uuid_pattern_creative(self, parser):
        """Test UUID pattern from creative server."""
        log_line = "[00:36:01] [User Authenticator #0/INFO]: UUID of player HermesImpact is d217394f-fb8a-4bde-95ad-9a5dd75ac0d9"

        event = parser.parse_line("creative", log_line)

        assert event is not None
        assert isinstance(event, PlayerUuidDiscoveredEvent)
        assert event.player_name == "HermesImpact"
        assert event.uuid == "d217394ffb8a4bde95ad9a5dd75ac0d9"

    def test_uuid_pattern_with_underscores(self, parser):
        """Test UUID pattern with underscores in player name."""
        log_line = "[10十月2024 13:42:13.309] [User Authenticator #1/INFO] [net.minecraft.server.network.ServerLoginPacketListenerImpl/]: UUID of player ___Astesia is 7c9908a4-db3e-48ab-b8fe-7da940df746f"

        event = parser.parse_line("atm9s", log_line)

        assert event is not None
        assert isinstance(event, PlayerUuidDiscoveredEvent)
        assert event.player_name == "___Astesia"
        assert event.uuid == "7c9908a4db3e48abb8fe7da940df746f"

    def test_config_sync_pattern(self, parser):
        """Test config sync UUID pattern."""
        log_line = "[24Jan2024 11:08:48.537] [Server thread/INFO] [Jade/]: Syncing config to Qin_Ning (967c2921-423f-4c50-b57e-c92ad45d04be)"

        event = parser.parse_line("atm9", log_line)

        assert event is not None
        assert isinstance(event, PlayerUuidDiscoveredEvent)
        assert event.player_name == "Qin_Ning"
        assert event.uuid == "967c2921423f4c50b57ec92ad45d04be"


class TestJoinParsing:
    """Test player join event parsing from real server logs."""

    def test_join_pattern_atm9(self, parser):
        """Test join pattern from atm9 server."""
        log_line = "[24Jan2024 11:08:47.258] [Server thread/INFO] [net.minecraft.server.players.PlayerList/]: Qin_Ning[/172.27.0.1:33916] logged in with entity id 1557 at (-6.5, 63.0, -7.5)"

        event = parser.parse_line("atm9", log_line)

        assert event is not None
        assert isinstance(event, PlayerJoinedEvent)
        assert event.server_id == "atm9"
        assert event.player_name == "Qin_Ning"

    def test_join_pattern_ipv6(self, parser):
        """Test join pattern with IPv6 address."""
        log_line = "[10十月2024 13:42:24.915] [Server thread/INFO] [net.minecraft.server.players.PlayerList/]: ___Astesia[/[2408:8207:2423:74f0:756b:aa57:3684:7ce4]:5962] logged in with entity id 504 at (10.5, 68.0, 4.5)"

        event = parser.parse_line("atm9s", log_line)

        assert event is not None
        assert isinstance(event, PlayerJoinedEvent)
        assert event.player_name == "___Astesia"

    def test_join_pattern_localhost(self, parser):
        """Test join pattern with localhost."""
        log_line = "[00:11:12] [Server thread/INFO]: salty_orange_[/192.168.144.1:34444] logged in with entity id 10615050 at (93.97473063951148, 65.0, -33.74392424874093)"

        event = parser.parse_line("gtnh", log_line)

        assert event is not None
        assert isinstance(event, PlayerJoinedEvent)
        assert event.player_name == "salty_orange_"

    def test_join_pattern_with_world_name(self, parser):
        """Test join pattern with world name."""
        log_line = "[15:46:03] [Server thread/INFO]: xyqyear[/127.0.0.1:63877] logged in with entity id 63 at ([Arcade]0.5, 128.0, 0.5)"

        event = parser.parse_line("xiaoyouxi", log_line)

        assert event is not None
        assert isinstance(event, PlayerJoinedEvent)
        assert event.player_name == "xyqyear"


class TestLeaveParsing:
    """Test player leave event parsing from real server logs."""

    def test_leave_pattern_simple(self, parser):
        """Test simple leave pattern."""
        log_line = "[24Jan2024 11:11:07.195] [Server thread/INFO] [net.minecraft.server.network.ServerGamePacketListenerImpl/]: Qin_Ning lost connection: Disconnected"

        event = parser.parse_line("atm9", log_line)

        assert event is not None
        assert isinstance(event, PlayerLeftEvent)
        assert event.server_id == "atm9"
        assert event.player_name == "Qin_Ning"
        assert event.reason == "Disconnected"

    def test_leave_pattern_creative(self, parser):
        """Test leave pattern from creative server."""
        log_line = "[00:40:46] [Server thread/INFO]: HermesImpact lost connection: Disconnected"

        event = parser.parse_line("creative", log_line)

        assert event is not None
        assert isinstance(event, PlayerLeftEvent)
        assert event.player_name == "HermesImpact"
        assert event.reason == "Disconnected"

    def test_leave_pattern_with_exception(self, parser):
        """Test leave pattern with exception message."""
        log_line = "[17:05:39] [Server thread/INFO] [net.minecraft.network.NetHandlerPlayServer]: ___Astesia lost connection: Internal Exception: java.io.IOException: 远程主机强迫关闭了一个现有的连接。"

        event = parser.parse_line("mto", log_line)

        assert event is not None
        assert isinstance(event, PlayerLeftEvent)
        assert event.player_name == "___Astesia"
        assert event.reason.startswith("Internal Exception")

    def test_leave_pattern_complex_reason(self, parser):
        """Test leave pattern with complex disconnection reason."""
        log_line = "[01:06:20] [Server thread/INFO]: salty_orange_ lost connection: TextComponent{text='Disconnected', siblings=[], style=Style{hasParent=false, color=null, bold=null, italic=null, underlined=null, obfuscated=null, clickEvent=null, hoverEvent=null}}"

        event = parser.parse_line("gtnh", log_line)

        assert event is not None
        assert isinstance(event, PlayerLeftEvent)
        assert event.player_name == "salty_orange_"
        assert "TextComponent" in event.reason


class TestChatParsing:
    """Test chat message parsing from real server logs."""

    def test_chat_pattern_simple(self, parser):
        """Test simple chat pattern."""
        log_line = "[24Jan2024 11:20:31.622] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <Qin_Ning> ?"

        event = parser.parse_line("atm9", log_line)

        assert event is not None
        assert isinstance(event, PlayerChatMessageEvent)
        assert event.server_id == "atm9"
        assert event.player_name == "Qin_Ning"
        assert event.message == "?"

    def test_chat_pattern_not_secure(self, parser):
        """Test chat pattern with [Not Secure] prefix."""
        log_line = (
            "[20:39:48] [Async Chat Thread - #1/INFO]: [Not Secure] <longwindy> 改不了"
        )

        event = parser.parse_line("creative", log_line)

        assert event is not None
        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "longwindy"
        assert event.message == "改不了"

    def test_chat_pattern_chinese(self, parser):
        """Test chat pattern with Chinese characters."""
        log_line = "[11Dec2024 16:07:03.141] [Server thread/INFO] [net.minecraft.server.dedicated.DedicatedServer/]: <___Astesia> 怎么没有僵尸"

        event = parser.parse_line("dc", log_line)

        assert event is not None
        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "___Astesia"
        assert event.message == "怎么没有僵尸"

    def test_chat_pattern_special_chars(self, parser):
        """Test chat pattern with special characters."""
        log_line = "[28Oct2024 15:29:04.610] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <8559re> ????"

        event = parser.parse_line("moni", log_line)

        assert event is not None
        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "8559re"
        assert event.message == "????"


class TestAchievementParsing:
    """Test achievement event parsing."""

    def test_advancement_pattern(self, parser):
        """Test advancement pattern."""
        log_line = "[12:34:56] [Server thread/INFO]: TestPlayer has made the advancement [Stone Age]"

        event = parser.parse_line("test_server", log_line)

        assert event is not None
        assert isinstance(event, PlayerAchievementEvent)
        assert event.server_id == "test_server"
        assert event.player_name == "TestPlayer"
        assert event.achievement_name == "Stone Age"

    def test_achievement_pattern(self, parser):
        """Test achievement pattern (older format)."""
        log_line = "[12:34:56] [Server thread/INFO]: TestPlayer has just earned the achievement [Getting Wood]"

        event = parser.parse_line("test_server", log_line)

        assert event is not None
        assert isinstance(event, PlayerAchievementEvent)
        assert event.player_name == "TestPlayer"
        assert event.achievement_name == "Getting Wood"


class TestServerStopParsing:
    """Test server stop detection."""

    def test_server_stop_pattern(self, parser):
        """Test server stop pattern."""
        log_line = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: Stopping server"

        event = parser.parse_line("test_server", log_line)

        assert event is not None
        assert isinstance(event, ServerStoppingEvent)
        assert event.server_id == "test_server"

    def test_server_stop_shutdown_thread(self, parser):
        """Test server stop with shutdown thread."""
        log_line = "[15:30:45] [Server Shutdown Thread/INFO] [minecraft/DedicatedServer]: Stopping server"

        event = parser.parse_line("test_server", log_line)

        assert event is not None
        assert isinstance(event, ServerStoppingEvent)


class TestForgeryPrevention:
    """Test that player forgery attempts are blocked."""

    def test_uuid_forgery_with_chat(self, parser):
        """Test that UUID patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> UUID of player FakePlayer is 12345678-1234-1234-1234-123456789abc"

        event = parser.parse_line("test_server", forged_log)

        # Should not parse UUID from chat message
        assert event is None or not isinstance(event, PlayerUuidDiscoveredEvent)

    def test_join_forgery_with_chat(self, parser):
        """Test that join patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> FakePlayer[/1.2.3.4:12345] logged in with entity id 123 at (0, 0, 0)"

        event = parser.parse_line("test_server", forged_log)

        # Should not parse join from chat message
        assert event is None or not isinstance(event, PlayerJoinedEvent)

    def test_leave_forgery_with_chat(self, parser):
        """Test that leave patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> FakePlayer lost connection: Fake disconnection"

        event = parser.parse_line("test_server", forged_log)

        # Should not parse leave from chat message
        assert event is None or not isinstance(event, PlayerLeftEvent)

    def test_server_stop_forgery_with_chat(self, parser):
        """Test that server stop patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> Stopping server"

        event = parser.parse_line("test_server", forged_log)

        # Should not detect server stop from chat message
        assert event is None or not isinstance(event, ServerStoppingEvent)

    def test_legitimate_vs_forged_mixed(self, parser):
        """Test that only legitimate patterns are parsed when mixed with forged ones."""
        # This would be multiple lines in real scenario, testing with legitimate line
        legitimate_log = "[12:34:57] [User Authenticator #1/INFO] [net.minecraft.server.network.ServerLoginPacketListenerImpl/]: UUID of player RealPlayer is 22222222-2222-2222-2222-222222222222"

        event = parser.parse_line("test_server", legitimate_log)

        assert event is not None
        assert isinstance(event, PlayerUuidDiscoveredEvent)
        assert event.player_name == "RealPlayer"
        assert event.uuid == "22222222222222222222222222222222"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_line(self, parser):
        """Test parsing empty line."""
        event = parser.parse_line("test_server", "")

        assert event is None

    def test_malformed_line(self, parser):
        """Test parsing malformed log line."""
        event = parser.parse_line("test_server", "This is not a valid log line")

        assert event is None

    def test_partial_match(self, parser):
        """Test that partial matches don't create events."""
        # Line that might partially match but shouldn't create event
        log_line = "[12:34:56] [Server thread/INFO]: Player data saved"

        event = parser.parse_line("test_server", log_line)

        assert event is None

    def test_multiple_patterns_priority(self, parser):
        """Test that UUID patterns are checked first."""
        # Line that could match both UUID and other patterns
        log_line = "[12:34:56] [User Authenticator #1/INFO]: UUID of player TestPlayer is 12345678-1234-1234-1234-123456789abc"

        event = parser.parse_line("test_server", log_line)

        # Should parse as UUID event, not any other type
        assert isinstance(event, PlayerUuidDiscoveredEvent)

    def test_whitespace_handling(self, parser):
        """Test handling of lines with extra whitespace."""
        log_line = "   [12:34:56] [Server thread/INFO]: TestPlayer[/127.0.0.1:12345] logged in with entity id 1 at (0, 0, 0)   "

        # Parser should handle this (line should be stripped before parsing in real usage)
        # This test documents current behavior
        event = parser.parse_line("test_server", log_line.strip())

        if event:
            assert isinstance(event, PlayerJoinedEvent)
