"""Log parser configuration."""

import re
from typing import Annotated

from pydantic import ConfigDict, Field

from ..schemas import BaseConfigSchema


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
            default=r"^(?!.*<).* (\S+)\[/.*?\] logged in with entity",
        ),
    ]

    leave_pattern: Annotated[
        str,
        Field(
            title="玩家离开解析规则",
            description="正则表达式模式，用于解析玩家离开事件",
            default=r"^(?!.*<).* (\S+) lost connection: (.*)",
        ),
    ]

    server_stop_pattern: Annotated[
        str,
        Field(
            title="服务器停止解析规则",
            description="正则表达式模式，用于检测服务器停止事件",
            default=r"^(?!.*<).*Stopping server",
        ),
    ]

    chat_pattern: Annotated[
        str,
        Field(
            title="聊天消息解析规则",
            description="正则表达式模式；第 1 组为可选前缀，第 2 组为玩家名，第 3 组为消息",
            default=r": (\[Not Secure\] )?<(\S+)> (.*)",
        ),
    ]

    achievement_patterns: Annotated[
        list[str],
        Field(
            title="成就解析规则",
            description="正则表达式模式列表，用于解析玩家获得成就事件",
            default_factory=lambda: [
                r"^(?!.*<).*\]: (.+) has made the advancement \[(.*)\]",
                r"^(?!.*<).* (\S+) has just earned the achievement \[(.*)\]",
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
