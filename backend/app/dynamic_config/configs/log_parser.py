"""Log parser configuration."""

from typing import Annotated, List

from pydantic import Field

from ..schemas import BaseConfigSchema


class LogParserConfig(BaseConfigSchema):
    """
    Configuration for Minecraft server log parsing patterns.

    ! Note: Please change the patterns here and test them before modifying the values in the UI.
    """

    uuid_patterns: Annotated[
        List[str],
        Field(
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
            description="正则表达式模式，用于解析玩家加入事件",
            default=r"^(?!.*<).* (\S+)\[/.*?\] logged in with entity",
        ),
    ]

    leave_pattern: Annotated[
        str,
        Field(
            description="正则表达式模式，用于解析玩家离开事件",
            default=r"^(?!.*<).* (\S+) lost connection: (.*)",
        ),
    ]

    server_stop_pattern: Annotated[
        str,
        Field(
            description="正则表达式模式，用于检测服务器停止事件",
            default=r"^(?!.*<).*Stopping server",
        ),
    ]

    chat_pattern: Annotated[
        str,
        Field(
            description="正则表达式模式，用于解析聊天消息",
            default=r": (\[Not Secure\] )?<(\S+)> (.*)",
        ),
    ]

    achievement_patterns: Annotated[
        List[str],
        Field(
            description="正则表达式模式列表，用于解析玩家获得成就事件",
            default_factory=lambda: [
                r"^(?!.*<).*\]: (.+) has made the advancement \[(.*)\]",
                r"^(?!.*<).* (\S+) has just earned the achievement \[(.*)\]",
            ],
        ),
    ]
