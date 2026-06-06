from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator

from ..schemas import BaseConfigSchema


class DNSPod(BaseConfigSchema):
    model_config = ConfigDict(title="DNSPod 配置")

    type: Annotated[Literal["dnspod"], Field(title="DNS 提供商类型", description="DNS 提供商的类型。")] = "dnspod"
    domain: Annotated[str, Field(title="域名", description="要管理的域名。")] = "example.com"
    id: Annotated[
        str,
        Field(title="DNSPod API 标识", description="用于访问 DNSPod API 的 ID。"),
    ] = "id"
    key: Annotated[str, Field(title="DNSPod API 密钥", description="DNSPod API 密钥。")] = "key"


class Huawei(BaseConfigSchema):
    model_config = ConfigDict(title="华为云 DNS 配置")

    type: Annotated[Literal["huawei"], Field(title="DNS 提供商类型", description="DNS 提供商的类型。")] = "huawei"
    domain: Annotated[str, Field(title="域名", description="要管理的域名。")] = "example.com"
    ak: Annotated[str, Field(title="访问密钥 ID", description="华为云访问密钥 ID。")] = "id"
    sk: Annotated[str, Field(title="秘密访问密钥", description="华为云秘密访问密钥。")] = "key"
    region: Annotated[str, Field(title="DNS 区域", description="华为云 DNS 区域。")] = "cn-south-1"


class Manual(BaseConfigSchema):
    model_config = ConfigDict(title="手动地址配置")

    type: Annotated[Literal["manual"], Field(title="地址配置类型", description="地址配置的类型。")] = "manual"
    name: Annotated[str, Field(title="地址名称", description="地址名称。")] = "*"
    record_type: Annotated[
        Literal["A", "AAAA", "CNAME"], Field(title="DNS 记录类型", description="DNS 记录的类型。")
    ] = "A"
    value: Annotated[str, Field(title="记录值", description="IP 地址或 CNAME 目标。")] = "127.0.0.1"
    port: Annotated[int, Field(title="端口号", description="服务器端口号。")] = 25565


class DNSManagerConfig(BaseConfigSchema):
    model_config = ConfigDict(title="DNS 管理配置")

    enabled: Annotated[bool, Field(title="启用 DNS 管理", description="是否启用 DNS 管理器。")] = False
    dns: Annotated[
        Huawei | DNSPod,
        Field(title="DNS 提供商配置", description="DNS 提供商配置。", discriminator="type"),
    ] = Huawei()
    managed_sub_domain: Annotated[str, Field(title="托管子域名", description="由 MC Admin 管理的子域名。")] = "mc"

    mc_router_base_url: Annotated[str, Field(title="mc-router 基础 URL", description="mc-router 的基础 URL。")] = (
        "http://127.0.0.1:26666"
    )

    dns_ttl: Annotated[
        int,
        Field(title="DNS 生存时间", description="DNS TTL（生存时间）值。"),
    ] = 15

    addresses: Annotated[
        list[Manual],
        Field(title="地址配置列表", description="手动地址配置列表。", default_factory=list),
    ]

    # validate addresses list can not have duplicates of name
    @field_validator("addresses")
    def check_no_duplicate_names(cls, v: list[Manual]) -> list[Manual]:
        names = [addr.name for addr in v]
        if len(names) != len(set(names)):
            raise ValueError("地址配置列表中不能有重复的名称")
        return v
