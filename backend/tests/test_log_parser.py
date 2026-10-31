"""Test cases for LogParser using real Minecraft server logs."""

import pytest

from app.log_monitor.events import (
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from app.log_monitor.parser import LogParser


@pytest.fixture
def parser(runtime_config):
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

    @pytest.mark.parametrize(
        ("address", "location"),
        [
            pytest.param("/[2001:db8::1]:25565", " at (0.0, 64.0, 0.0)", id="ipv6"),
            pytest.param("IP hidden", "", id="hidden-address"),
            pytest.param("local", " at (0.0, 64.0, 0.0)", id="local"),
            pytest.param("/192.0.2.4:25565", " in world(0) at (0.0, 64.0, 0.0)", id="sponge-world"),
            pytest.param("/192.0.2.4:25565", " in DIM-1(-1) at (0.0, 64.0, 0.0)", id="sponge-dimension"),
        ],
    )
    def test_join_supported_connection_forms(self, parser, address, location):
        log_line = (
            f"[12:34:56] [Server thread/INFO]: Alex[{address}]"
            f" logged in with entity id -42{location}"
        )

        event = parser.parse_line("server", log_line)

        assert isinstance(event, PlayerJoinedEvent)
        assert event.server_id == "server"
        assert event.player_name == "Alex"

    @pytest.mark.parametrize(
        "body",
        [
            "Copied Alex[/192.0.2.4:25565] logged in with entity id 42",
            "Maple Fox[/192.0.2.4:25565] logged in with entity id 42",
            "Alex[/192.0.2.4:25565] logged in with entity id 42; historical entry",
        ],
    )
    def test_join_ignores_narrative_and_unsupported_names(self, parser, body):
        assert parser.parse_line("server", f"[12:34:56] [Server thread/INFO]: {body}") is None


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

    @pytest.mark.parametrize(
        "subject",
        [
            pytest.param("Alex (/192.0.2.4:25565)", id="named-ipv4"),
            pytest.param("Alex (/[2001:db8::1]:25565)", id="named-ipv6"),
            pytest.param("/192.0.2.4:25565", id="address-only"),
            pytest.param("192.0.2.4", id="bare-ipv4"),
            pytest.param(
                "com.mojang.authlib.GameProfile@abc["
                "id=12345678-1234-1234-1234-123456789abc,name=Alex,properties={}] "
                "(/192.0.2.4:25565)",
                id="game-profile",
            ),
            pytest.param("Maple Fox", id="whitespace-name"),
            pytest.param("Disconnecting Alex", id="narrative-prefix"),
        ],
    )
    def test_leave_pattern_ignores_connection_subjects(self, parser, subject):
        log_line = f"[12:34:56] [Server thread/INFO]: {subject} lost connection: Disconnected"

        assert parser.parse_line("server", log_line) is None

    @pytest.mark.parametrize(
        ("spacing", "reason"),
        [
            pytest.param("  ", "Disconnected", id="double-space-header"),
            pytest.param(" ", "Timed out; Relay lost connection: Disconnected", id="nested-reason"),
        ],
    )
    def test_leave_pattern_preserves_name_and_reason(self, parser, spacing, reason):
        log_line = f"[12:34:56] [Server thread/INFO]:{spacing}Alex lost connection: {reason}"

        event = parser.parse_line("server", log_line)

        assert isinstance(event, PlayerLeftEvent)
        assert event.player_name == "Alex"
        assert event.reason == reason

    def test_leave_pattern_requires_log_header(self, parser):
        assert parser.parse_line("server", "Alex lost connection: Disconnected") is None


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

    @pytest.mark.parametrize(
        ("body", "player_name"),
        [
            pytest.param("<Alex> hello", "Alex", id="ordinary"),
            pytest.param("[Not Secure] <Alex> hello", "Alex", id="not-secure"),
            pytest.param("<<>> hello", "<>", id="legacy-name"),
        ],
    )
    def test_chat_with_nested_logger(self, parser, body, player_name):
        event = parser.parse_line(
            "server", f"[12:34:56] [Server thread/INFO] [M3[INFO]/]: {body}"
        )

        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == player_name
        assert event.message == "hello"

    @pytest.mark.parametrize(
        "line",
        [
            "[12:34:56] [main/DEBUG]: Patching method: <init> (<init>)",
            "[12:34:56] [main/ERROR]: Invalid type override entry: <item:example> ignored",
            '[12:34:56][DONE][SERVER][INFO] Adding recipe, output: <item:example> * 4',
            "[12:34:56] [Server thread/INFO]: Copied [Other/INFO]: <Alex> hello",
        ],
    )
    def test_chat_ignores_diagnostic_fragments(self, parser, line):
        assert parser.parse_line("server", line) is None


class TestAchievementParsing:
    """Test achievement event parsing."""

    @pytest.mark.parametrize(
        ("verb", "title"),
        [
            pytest.param("has made the advancement", "Stone Age", id="task"),
            pytest.param("has reached the goal", "A Balanced Diet", id="goal"),
            pytest.param("has completed the challenge", "A Furious Cocktail", id="challenge"),
            pytest.param("has just earned the achievement", "Getting Wood", id="legacy"),
        ],
    )
    def test_achievement_announcement_forms(self, parser, verb, title):
        log_line = f"[12:34:56] [Server thread/INFO]: Alex {verb} [{title}]"

        event = parser.parse_line("test_server", log_line)

        assert isinstance(event, PlayerAchievementEvent)
        assert event.server_id == "test_server"
        assert event.player_name == "Alex"
        assert event.achievement_name == title

    @pytest.mark.parametrize(
        ("subject", "title", "expected_title"),
        [
            pytest.param(
                "Alex the Mighty", "[Nested [Title]]", "Nested [Title]", id="display-title"
            ),
            pytest.param(
                "\x1b[32mAlex the Mighty\x1b[0m",
                "\x1b[35m[Nested [A < B > C]]\x1b[0m",
                "Nested [A < B > C]",
                id="boundary-colors",
            ),
        ],
    )
    def test_achievement_preserves_display_and_title(self, parser, subject, title, expected_title):
        log_line = (
            f"[12:34:56] [Server thread/INFO]: {subject}"
            f" has completed the challenge {title}"
        )

        event = parser.parse_line("test_server", log_line)

        assert isinstance(event, PlayerAchievementEvent)
        assert event.player_name == "Alex the Mighty"
        assert event.achievement_name == expected_title

    @pytest.mark.parametrize(
        "body",
        [
            "Alex has completed the challenge []",
            "<> has made the advancement [Stone Age]",
            "Al\x1b[32mex has reached the goal [A Balanced Diet]",
            "Alex has reached the goal [A \x1b[32mBalanced Diet]",
        ],
    )
    def test_achievement_ignores_empty_fields_and_internal_escapes(self, parser, body):
        assert parser.parse_line("server", f"[12:34:56] [Server thread/INFO]: {body}") is None


class TestServerStopParsing:
    """Test server stop detection."""

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param("Stopping server", id="ordinary"),
            pytest.param(
                "Stopping server (Ignore any thread death message you see! - DO NOT REPORT THREAD DEATH TO PAPER)",
                id="paper",
            ),
            pytest.param("Startup script './start.sh' does not exist! Stopping server.", id="missing-script"),
        ],
    )
    def test_server_stop_pattern(self, parser, body):
        log_line = f"[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: {body}"

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

    @pytest.mark.parametrize(
        "body",
        [
            "Mod diagnostic: Stopping server",
            "Stopping server in 30 seconds",
            "Stopping server (historical entry)",
        ],
    )
    def test_server_stop_ignores_narrative(self, parser, body):
        assert parser.parse_line("server", f"[12:34:56] [Server thread/INFO]: {body}") is None


class TestForgeryPrevention:
    """Test that player forgery attempts are blocked."""

    def test_uuid_forgery_with_chat(self, parser):
        """Test that UUID patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> UUID of player FakePlayer is 12345678-1234-1234-1234-123456789abc"

        event = parser.parse_line("test_server", forged_log)

        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "EvilPlayer"
        assert event.message == "UUID of player FakePlayer is 12345678-1234-1234-1234-123456789abc"

    def test_join_forgery_with_chat(self, parser):
        """Test that join patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> FakePlayer[/1.2.3.4:12345] logged in with entity id 123 at (0, 0, 0)"

        event = parser.parse_line("test_server", forged_log)

        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "EvilPlayer"
        assert event.message == "FakePlayer[/1.2.3.4:12345] logged in with entity id 123 at (0, 0, 0)"

    def test_leave_forgery_with_chat(self, parser):
        """Test that leave patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> FakePlayer lost connection: Fake disconnection"

        event = parser.parse_line("test_server", forged_log)

        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "EvilPlayer"
        assert event.message == "FakePlayer lost connection: Fake disconnection"

    def test_server_stop_forgery_with_chat(self, parser):
        """Test that server stop patterns in chat messages are ignored."""
        forged_log = "[12:34:56] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: <EvilPlayer> Stopping server"

        event = parser.parse_line("test_server", forged_log)

        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "EvilPlayer"
        assert event.message == "Stopping server"

    @pytest.mark.parametrize(
        "verb",
        [
            "has made the advancement",
            "has reached the goal",
            "has completed the challenge",
            "has just earned the achievement",
        ],
    )
    def test_achievement_wording_remains_chat(self, parser, verb):
        message = f"OtherPlayer {verb} [A < B]"
        event = parser.parse_line(
            "server", f"[12:34:56] [Server thread/INFO]: <Alex> {message}"
        )

        assert isinstance(event, PlayerChatMessageEvent)
        assert event.player_name == "Alex"
        assert event.message == message

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

    @pytest.mark.parametrize(
        "line",
        [
            "Alex[/192.0.2.4:25565] logged in with entity id 42",
            "Diagnostic: <Alex> hello",
            "Alex has just earned the achievement [Getting Wood]",
            "Stopping server",
        ],
    )
    def test_default_messages_require_structured_headers(self, parser, line):
        assert parser.parse_line("server", line) is None

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
