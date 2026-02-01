"""Template system configuration schema."""

from typing import Annotated, Literal, Optional

from pydantic import Field, model_validator

from ..schemas import BaseConfigSchema


class IntVarConfig(BaseConfigSchema):
    """Integer variable configuration."""

    type: Literal["int"] = Field("int", description="变量类型")
    name: Annotated[str, Field(min_length=1, max_length=50, description="变量名称")]
    display_name: Annotated[
        str, Field(min_length=1, max_length=100, description="显示名称")
    ]
    description: Annotated[Optional[str], Field(description="变量描述")] = None
    default: Annotated[Optional[int], Field(description="默认值")] = None
    min_value: Annotated[Optional[int], Field(description="最小值")] = None
    max_value: Annotated[Optional[int], Field(description="最大值")] = None


class FloatVarConfig(BaseConfigSchema):
    """Float variable configuration."""

    type: Literal["float"] = Field("float", description="变量类型")
    name: Annotated[str, Field(min_length=1, max_length=50, description="变量名称")]
    display_name: Annotated[
        str, Field(min_length=1, max_length=100, description="显示名称")
    ]
    description: Annotated[Optional[str], Field(description="变量描述")] = None
    default: Annotated[Optional[float], Field(description="默认值")] = None
    min_value: Annotated[Optional[float], Field(description="最小值")] = None
    max_value: Annotated[Optional[float], Field(description="最大值")] = None


class StringVarConfig(BaseConfigSchema):
    """String variable configuration."""

    type: Literal["string"] = Field("string", description="变量类型")
    name: Annotated[str, Field(min_length=1, max_length=50, description="变量名称")]
    display_name: Annotated[
        str, Field(min_length=1, max_length=100, description="显示名称")
    ]
    description: Annotated[Optional[str], Field(description="变量描述")] = None
    default: Annotated[Optional[str], Field(description="默认值")] = None
    max_length: Annotated[Optional[int], Field(description="最大长度")] = None
    pattern: Annotated[Optional[str], Field(description="正则表达式模式")] = None


class EnumVarConfig(BaseConfigSchema):
    """Enum variable configuration."""

    type: Literal["enum"] = Field("enum", description="变量类型")
    name: Annotated[str, Field(min_length=1, max_length=50, description="变量名称")]
    display_name: Annotated[
        str, Field(min_length=1, max_length=100, description="显示名称")
    ]
    description: Annotated[Optional[str], Field(description="变量描述")] = None
    default: Annotated[Optional[str], Field(description="默认值")] = None
    options: list[str] = Field(min_length=1, description="可选值列表")

    @model_validator(mode="after")
    def validate_default_in_options(self) -> "EnumVarConfig":
        """Validate that default value is one of the options."""
        if self.default is not None and self.default not in self.options:
            raise ValueError(
                f"默认值 '{self.default}' 必须是选项列表中的一个: {self.options}"
            )
        return self


class BoolVarConfig(BaseConfigSchema):
    """Boolean variable configuration."""

    type: Literal["bool"] = Field("bool", description="变量类型")
    name: Annotated[str, Field(min_length=1, max_length=50, description="变量名称")]
    display_name: Annotated[
        str, Field(min_length=1, max_length=100, description="显示名称")
    ]
    description: Annotated[Optional[str], Field(description="变量描述")] = None
    default: Annotated[Optional[bool], Field(description="默认值")] = None


SystemVariableConfig = Annotated[
    IntVarConfig | StringVarConfig | EnumVarConfig | FloatVarConfig | BoolVarConfig,
    Field(discriminator="type"),
]


class TemplatesConfig(BaseConfigSchema):
    """模板系统配置"""

    system_variables: Annotated[
        list[SystemVariableConfig], Field(description="系统保留变量定义列表")
    ] = [
        StringVarConfig(
            type="string",
            name="name",
            display_name="服务器名称",
            description="服务器名称，用于 container_name (mc-{name})",
            max_length=20,
            pattern="^[a-z0-9-_]+$",
        ),
        EnumVarConfig(
            type="enum",
            name="java_version",
            display_name="Java 版本",
            description="服务器使用的 Java 版本",
            options=["8", "11", "17", "21", "25"],
        ),
        StringVarConfig(
            type="string",
            name="game_version",
            display_name="游戏版本",
            description="Minecraft 游戏版本",
        ),
        IntVarConfig(
            type="int",
            name="max_memory",
            display_name="最大内存 (GB)",
            description="服务器最大内存分配，单位为 GB",
            default=6,
            min_value=1,
            max_value=16,
        ),
        IntVarConfig(
            type="int",
            name="game_port",
            display_name="游戏端口",
            description="Minecraft 服务器端口",
            min_value=1024,
            max_value=65535,
        ),
        IntVarConfig(
            type="int",
            name="rcon_port",
            display_name="RCON 端口",
            description="RCON 管理端口",
            min_value=1024,
            max_value=65535,
        ),
    ]
