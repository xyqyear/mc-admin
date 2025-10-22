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
            if match and len(match.groups()) >= 2:
                player_name = match.group(1)
                uuid_str = match.group(2)
                if player_name and uuid_str:
                    uuid = uuid_str.replace("-", "")  # Remove dashes
                    logger.info(f"Parsed UUID discovery: {player_name} = {uuid}")
                    return PlayerUuidDiscoveredEvent(
                        server_id=server_id,
                        player_name=player_name,
                        uuid=uuid,
                    )
                else:
                    logger.warning(
                        f"Failed to extract UUID from line (empty groups): {line}"
                    )
                    continue

        # Try join pattern
        match = re.search(parser_config.join_pattern, line)
        if match and len(match.groups()) >= 1:
            player_name = match.group(1)
            if player_name:
                logger.info(f"Parsed player join: {player_name}")
                return PlayerJoinedEvent(
                    server_id=server_id,
                    player_name=player_name,
                )
            else:
                logger.warning(
                    f"Failed to extract join info from line (empty group): {line}"
                )

        # Try leave pattern
        match = re.search(parser_config.leave_pattern, line)
        if match and len(match.groups()) >= 1:
            player_name = match.group(1)
            if player_name:
                reason = match.group(2) if len(match.groups()) >= 2 else ""
                logger.info(f"Parsed player leave: {player_name}, reason: {reason}")
                return PlayerLeftEvent(
                    server_id=server_id,
                    player_name=player_name,
                    reason=reason,
                )
            else:
                logger.warning(
                    f"Failed to extract leave info from line (empty group): {line}"
                )

        # Try chat pattern
        match = re.search(parser_config.chat_pattern, line)
        if match and len(match.groups()) >= 3:
            # Group 1 is [Not Secure] (optional), group 2 is player, group 3 is message
            player_name = match.group(2)
            message = match.group(3)
            if player_name and message:
                logger.info(f"Parsed chat message: <{player_name}> {message}")
                return PlayerChatMessageEvent(
                    server_id=server_id,
                    player_name=player_name,
                    message=message,
                )
            else:
                logger.warning(
                    f"Failed to extract chat info from line (empty groups): {line}"
                )

        # Try achievement patterns
        for achievement_pattern in parser_config.achievement_patterns:
            match = re.search(achievement_pattern, line)
            if match and len(match.groups()) >= 2:
                player_name = match.group(1)
                achievement_name = match.group(2)
                if player_name and achievement_name:
                    logger.info(
                        f"Parsed achievement: {player_name} earned {achievement_name}"
                    )
                    return PlayerAchievementEvent(
                        server_id=server_id,
                        player_name=player_name,
                        achievement_name=achievement_name,
                    )
                else:
                    logger.warning(
                        f"Failed to extract achievement info from line (empty groups): {line}"
                    )
                    continue

        # Try server stop pattern
        match = re.search(parser_config.server_stop_pattern, line)
        if match:
            logger.info(f"Parsed server stopping event for {server_id}")
            return ServerStoppingEvent(server_id=server_id)

        # No match
        return None
