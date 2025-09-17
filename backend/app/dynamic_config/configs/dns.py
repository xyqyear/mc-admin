from typing import Literal

from pydantic import Field

from ..schemas import BaseConfigSchema


class DNSPodParams(BaseConfigSchema):
    type: Literal["dnspod"] = Field(
        default="dnspod", description="DNS提供商的类型，请一定和DNSProviderConfig的type保持一致"
    )
    domain: str = Field(default="example.com", description="要管理的域名")
    id: str = Field(default="id", description="DNSPod API ID")
    key: str = Field(default="key", description="DNSPod API密钥")


class HuaweiParams(BaseConfigSchema):
    type: Literal["huawei"] = Field(
        default="huawei", description="DNS提供商的类型，请一定和DNSProviderConfig的type保持一致"
    )
    domain: str = Field(default="example.com", description="要管理的域名")
    ak: str = Field(default="id", description="访问密钥ID")
    sk: str = Field(default="key", description="秘密访问密钥")
    region: str = Field(default="cn-south-1", description="DNS区域")


class DNSProviderConfig(BaseConfigSchema):
    type: Literal["huawei", "dnspod"] = Field(
        default="huawei", description="DNS提供商的类型"
    )
    params: HuaweiParams | DNSPodParams = Field(
        default_factory=HuaweiParams, description="DNS提供商的参数"
    )


class NatmapMonitorConfig(BaseConfigSchema):
    enabled: bool = Field(
        default=False, description="是否启用Natmap监控器"
    )
    base_url: str = Field(
        default="http://127.0.0.1:8080",
        description="Natmap监控器的基础URL",
    )


class DockerWatcherConfig(BaseConfigSchema):
    enabled: bool = Field(
        default=False, description="是否启用Docker监控器"
    )
    # use settings.server_path for servers_root_path
    # servers_root_path: str = Field(
    #     default="/path/to/servers", description="The root path for the Docker servers"
    # )


class NatmapParams(BaseConfigSchema):
    type: Literal["natmap"] = Field(
        default="natmap", description="地址配置的类型，请一定和AddressConfig的type保持一致"
    )
    internal_port: int = Field(
        default=25565, description="Minecraft服务器的内部端口"
    )


class ManualParams(BaseConfigSchema):
    type: Literal["manual"] = Field(
        default="manual", description="地址配置的类型，请一定和AddressConfig的type保持一致"
    )
    record_type: Literal["A", "AAAA", "CNAME"] = Field(
        default="A", description="DNS记录的类型"
    )
    value: str = Field(default="127.0.0.1", description="IP地址")
    port: int = Field(default=25565, description="端口号")


class AddressConfig(BaseConfigSchema):
    type: Literal["natmap", "manual"] = Field(
        default="manual", description="地址配置的类型"
    )
    params: NatmapParams | ManualParams = Field(
        default=ManualParams(),
        description="地址配置的参数",
    )


class DNSManagerConfig(BaseConfigSchema):
    enabled: bool = Field(
        default=False, description="是否启用DNS管理器"
    )
    dns: DNSProviderConfig = Field(
        default_factory=DNSProviderConfig, description="DNS提供商配置"
    )
    managed_sub_domain: str = Field(default="mc", description="要管理的子域名")

    mc_router_base_url: str = Field(
        default="http://127.0.0.1:26666", description="mc-router的基础URL"
    )

    natmap_monitor: NatmapMonitorConfig = Field(
        default_factory=NatmapMonitorConfig,
        description="Natmap监控器配置",
    )
    docker_watcher: DockerWatcherConfig = Field(
        default_factory=DockerWatcherConfig,
        description="Docker监控器配置",
    )

    dns_ttl: int = Field(default=15, description="DNS TTL（生存时间）值")

    poll_interval: int = Field(
        default=15, description="轮询间隔（秒）"
    )

    addresses: list[AddressConfig] = Field(
        default_factory=list, description="地址配置列表"
    )
