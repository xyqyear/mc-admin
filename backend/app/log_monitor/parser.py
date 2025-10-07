"""Log parser for Minecraft server logs."""

import re
from typing import Optional

from ..dynamic_config import config
from ..events.base import (
    BaseEvent,
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from ..logger import logger


class LogParser:
    """Parses Minecraft server log lines and creates events."""

    def parse_line(self, server_id: str, line: str) -> Optional[BaseEvent]:
        """Parse a log line and return an event if matched.

        Args:
            server_id: Server identifier
            line: Log line to parse

        Returns:
            Parsed event or None if no match
        """
        # Get current configuration dynamically
        parser_config = config.log_parser

        # Try UUID patterns first
        for uuid_pattern in parser_config.uuid_patterns:
            match = re.search(uuid_pattern, line)
            if match:
                try:
                    player_name = match.group(1)
                    uuid = match.group(2).replace("-", "")  # Remove dashes
                    logger.debug(f"Parsed UUID discovery: {player_name} = {uuid}")
                    return PlayerUuidDiscoveredEvent(
                        server_id=server_id,
                        player_name=player_name,
                        uuid=uuid,
                    )
                except (IndexError, AttributeError) as e:
                    logger.warning(
                        f"Failed to extract UUID from line: {line}, error: {e}"
                    )
                    continue

        # Try join pattern
        match = re.search(parser_config.join_pattern, line)
        if match:
            try:
                player_name = match.group(1)
                logger.debug(f"Parsed player join: {player_name}")
                return PlayerJoinedEvent(
                    server_id=server_id,
                    player_name=player_name,
                )
            except (IndexError, AttributeError) as e:
                logger.warning(
                    f"Failed to extract join info from line: {line}, error: {e}"
                )

        # Try leave pattern
        match = re.search(parser_config.leave_pattern, line)
        if match:
            try:
                player_name = match.group(1)
                reason = match.group(2) if len(match.groups()) >= 2 else ""
                logger.debug(f"Parsed player leave: {player_name}, reason: {reason}")
                return PlayerLeftEvent(
                    server_id=server_id,
                    player_name=player_name,
                    reason=reason,
                )
            except (IndexError, AttributeError) as e:
                logger.warning(
                    f"Failed to extract leave info from line: {line}, error: {e}"
                )

        # Try chat pattern
        match = re.search(parser_config.chat_pattern, line)
        if match:
            try:
                # Group 1 is [Not Secure] (optional), group 2 is player, group 3 is message
                player_name = match.group(2)
                message = match.group(3)
                logger.debug(f"Parsed chat message: <{player_name}> {message}")
                return PlayerChatMessageEvent(
                    server_id=server_id,
                    player_name=player_name,
                    message=message,
                )
            except (IndexError, AttributeError) as e:
                logger.warning(
                    f"Failed to extract chat info from line: {line}, error: {e}"
                )

        # Try achievement patterns
        for achievement_pattern in parser_config.achievement_patterns:
            match = re.search(achievement_pattern, line)
            if match:
                try:
                    player_name = match.group(1)
                    achievement_name = match.group(2)
                    logger.debug(
                        f"Parsed achievement: {player_name} earned {achievement_name}"
                    )
                    return PlayerAchievementEvent(
                        server_id=server_id,
                        player_name=player_name,
                        achievement_name=achievement_name,
                    )
                except (IndexError, AttributeError) as e:
                    logger.warning(
                        f"Failed to extract achievement info from line: {line}, error: {e}"
                    )
                    continue

        # Try server stop pattern
        match = re.search(parser_config.server_stop_pattern, line)
        if match:
            logger.debug(f"Parsed server stopping event for {server_id}")
            return ServerStoppingEvent(server_id=server_id)

        # No match
        return None
