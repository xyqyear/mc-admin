from typing import Annotated, Literal, Union

from pydantic import Field

from ..schemas import BaseConfigSchema


class DNSPod(BaseConfigSchema):
    type: Annotated[Literal["dnspod"], Field(description="DNS提供商的类型")] = "dnspod"
    domain: Annotated[str, Field(description="要管理的域名")] = "example.com"
    id: Annotated[str, Field(description="DNSPod API ID")] = "id"
    key: Annotated[str, Field(description="DNSPod API密钥")] = "key"


class Huawei(BaseConfigSchema):
    type: Annotated[Literal["huawei"], Field(description="DNS提供商的类型")] = "huawei"
    domain: Annotated[str, Field(description="要管理的域名")] = "example.com"
    ak: Annotated[str, Field(description="访问密钥ID")] = "id"
    sk: Annotated[str, Field(description="秘密访问密钥")] = "key"
    region: Annotated[str, Field(description="DNS区域")] = "cn-south-1"


class NatmapMonitorConfig(BaseConfigSchema):
    enabled: Annotated[bool, Field(description="是否启用Natmap监控器")] = False
    base_url: Annotated[str, Field(description="Natmap监控器的基础URL")] = (
        "http://127.0.0.1:8080"
    )


class DockerWatcherConfig(BaseConfigSchema):
    enabled: Annotated[bool, Field(description="是否启用Docker监控器")] = False
    # use settings.server_path for servers_root_path
    # servers_root_path: Annotated[str, Field(default="/path/to/servers", description="The root path for the Docker servers")]


class Natmap(BaseConfigSchema):
    type: Annotated[Literal["natmap"], Field(description="地址配置的类型")] = "natmap"
    name: Annotated[str, Field(description="地址名称")] = "*"
    internal_port: Annotated[int, Field(description="Minecraft服务器的内部端口")] = (
        25565
    )


class Manual(BaseConfigSchema):
    type: Annotated[Literal["manual"], Field(description="地址配置的类型")] = "manual"
    name: Annotated[str, Field(description="地址名称")] = "*"
    record_type: Annotated[
        Literal["A", "AAAA", "CNAME"], Field(description="DNS记录的类型")
    ] = "A"
    value: Annotated[str, Field(description="IP地址")] = "127.0.0.1"
    port: Annotated[int, Field(description="端口号")] = 25565


class DNSManagerConfig(BaseConfigSchema):
    enabled: Annotated[bool, Field(description="是否启用DNS管理器")] = False
    dns: Annotated[
        Huawei | DNSPod,
        Field(description="DNS提供商配置", discriminator="type"),
    ] = Huawei()
    managed_sub_domain: Annotated[str, Field(description="要管理的子域名")] = "mc"

    mc_router_base_url: Annotated[str, Field(description="mc-router的基础URL")] = (
        "http://127.0.0.1:26666"
    )

    natmap_monitor: Annotated[
        NatmapMonitorConfig,
        Field(description="Natmap监控器配置"),
    ] = NatmapMonitorConfig()
    docker_watcher: Annotated[
        DockerWatcherConfig,
        Field(description="Docker监控器配置"),
    ] = DockerWatcherConfig()

    dns_ttl: Annotated[int, Field(description="DNS TTL（生存时间）值")] = 15

    poll_interval: Annotated[int, Field(description="轮询间隔（秒）")] = 15

    addresses: Annotated[
        list[Annotated[Union[Natmap, Manual], Field(discriminator="type")]],
        Field(description="地址配置列表", default_factory=list),
    ]
