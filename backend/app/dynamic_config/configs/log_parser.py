"""Log parser configuration."""

import re
from typing import Annotated

from pydantic import ConfigDict, Field

from ..schemas import BaseConfigSchema

_HEADER_BLOCK = r"\[(?:[^\[\]\r\n]|\[[^\[\]\r\n]*\])*\]"
_LOG_HEADER = rf"^(?:{_HEADER_BLOCK}[ \t]*)+:[ \t]*"
_GUARDED_LOG_HEADER = _LOG_HEADER.replace("^", "^(?!.*<)", 1)
_PLAYER_NAME = r"[^\s()[\]{}:/<>]+"
_SGR = r"(?:\x1b\[[0-9;]*m)*"
_ACHIEVEMENT_VERBS = (
    r"(?:has made the advancement|has completed the challenge|"
    r"has reached the goal|has just earned the achievement)"
)
_PAPER_STOP_SUFFIX = re.escape(
    " (Ignore any thread death message you see! - DO NOT REPORT THREAD DEATH TO PAPER)"
)


class LogParserConfig(BaseConfigSchema):
    """Configuration for Minecraft server log parsing patterns."""

    model_config = ConfigDict(title="日志解析配置")

    uuid_patterns: Annotated[
        list[str],
        Field(
            title="UUID 解析规则",
            description="正则表达式模式列表，用于解析玩家UUID信息",
            default_factory=lambda: [
                r"^(?!.*<).*UUID of player (\S+) is (\S{8}-\S{4}-\S{4}-\S{4}-\S{12})",
                r"^(?!.*<).*config to (\S+) \((\S{8}-\S{4}-\S{4}-\S{4}-\S{12})\)",
            ],
        ),
    ]

    join_pattern: Annotated[
        str,
        Field(
            title="玩家加入解析规则",
            description="正则表达式模式，用于解析玩家加入事件",
            default=(
                rf"{_GUARDED_LOG_HEADER}({_PLAYER_NAME})\[(?:/[^\r\n]*|IP hidden|local)\]"
                r" logged in with entity id -?\d+(?: in (?:world|DIM-?\d+)\(-?\d+\))?"
                r"(?: at \(.+\))?$"
            ),
        ),
    ]

    leave_pattern: Annotated[
        str,
        Field(
            title="玩家离开解析规则",
            description="正则表达式模式，用于解析玩家离开事件",
            default=(
                r"^(?!.*<)(?:\[[^\]\r\n]*\][ \t]*)+:[ \t]*"
                r"(?!\d{1,3}(?:\.\d{1,3}){3} lost connection: )"
                r"([^\s()[\]{}:/]+) lost connection: (.*)$"
            ),
        ),
    ]

    server_stop_pattern: Annotated[
        str,
        Field(
            title="服务器停止解析规则",
            description="正则表达式模式，用于检测服务器停止事件",
            default=(
                rf"{_GUARDED_LOG_HEADER}(?:Stopping server(?:{_PAPER_STOP_SUFFIX})?|"
                r"Startup script '[^'\r\n]+' does not exist! Stopping server\.)$"
            ),
        ),
    ]

    chat_pattern: Annotated[
        str,
        Field(
            title="聊天消息解析规则",
            description="正则表达式模式；第 1 组为可选前缀，第 2 组为玩家名，第 3 组为消息",
            default=_LOG_HEADER + r"(\[Not Secure\] )?<(\S+)> (.*)$",
        ),
    ]

    achievement_patterns: Annotated[
        list[str],
        Field(
            title="成就解析规则",
            description="正则表达式模式列表，用于解析玩家获得成就事件",
            default_factory=lambda: [
                (
                    rf"{_LOG_HEADER}{_SGR}([^<>\x1b\r\n]+?){_SGR} {_ACHIEVEMENT_VERBS} "
                    rf"{_SGR}\[([^\x1b\r\n]+)\]{_SGR}$"
                ),
            ],
        ),
    ]

    def validate_update(self) -> None:
        rules = [
            ("uuid_patterns", self.uuid_patterns, 2),
            ("join_pattern", [self.join_pattern], 1),
            ("leave_pattern", [self.leave_pattern], 1),
            ("server_stop_pattern", [self.server_stop_pattern], 0),
            ("chat_pattern", [self.chat_pattern], 3),
            ("achievement_patterns", self.achievement_patterns, 2),
        ]
        for field, patterns, groups in rules:
            for pattern in patterns:
                try:
                    compiled = re.compile(pattern)
                except re.error as exc:
                    raise ValueError(f"日志规则 {field} 的正则表达式无效：{exc}") from exc
                if compiled.groups < groups:
                    raise ValueError(f"日志规则 {field} 至少需要 {groups} 个捕获组")
