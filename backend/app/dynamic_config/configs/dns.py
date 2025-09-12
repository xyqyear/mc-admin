from typing import Literal

from pydantic import Field

from ..schemas import BaseConfigSchema


class DNSPodParams(BaseConfigSchema):
    type: Literal["dnspod"] = Field(
        default="dnspod", description="The type of DNS provider"
    )
    domain: str = Field(default="example.com", description="The domain name to manage")
    id: str = Field(default="id", description="The DNSPod API ID")
    key: str = Field(default="key", description="The DNSPod API Key")


class HuaweiParams(BaseConfigSchema):
    type: Literal["huawei"] = Field(
        default="huawei", description="The type of DNS provider"
    )
    domain: str = Field(default="example.com", description="The domain name to manage")
    ak: str = Field(default="id", description="AK")
    sk: str = Field(default="key", description="SK")
    region: str = Field(default="cn-south-1", description="DNS region")


class DNSProviderConfig(BaseConfigSchema):
    type: Literal["huawei", "dnspod"] = Field(
        default="huawei", description="The type of DNS provider"
    )
    params: HuaweiParams | DNSPodParams = Field(
        default_factory=HuaweiParams, description="The parameters for the DNS provider"
    )


class NatmapMonitorConfig(BaseConfigSchema):
    enabled: bool = Field(
        default=False, description="Whether the Natmap monitor is enabled"
    )
    base_url: str = Field(
        default="http://127.0.0.1:8080",
        description="The base URL for the Natmap monitor",
    )


class DockerWatcherConfig(BaseConfigSchema):
    enabled: bool = Field(
        default=False, description="Whether the Docker watcher is enabled"
    )
    # use settings.server_path for servers_root_path
    # servers_root_path: str = Field(
    #     default="/path/to/servers", description="The root path for the Docker servers"
    # )


class NatmapParams(BaseConfigSchema):
    type: Literal["natmap"] = Field(
        default="natmap", description="The type of address configuration"
    )
    internal_port: int = Field(
        default=25565, description="The internal port of the Minecraft server"
    )


class ManualParams(BaseConfigSchema):
    type: Literal["manual"] = Field(
        default="manual", description="The type of address configuration"
    )
    record_type: Literal["A", "AAAA", "CNAME"] = Field(
        default="A", description="The type of DNS record"
    )
    value: str = Field(default="127.0.0.1", description="The IP address")
    port: int = Field(default=25565, description="The port number")


class AddressConfig(BaseConfigSchema):
    type: Literal["natmap", "manual"] = Field(
        default="manual", description="The type of address configuration"
    )
    params: NatmapParams | ManualParams = Field(
        default=ManualParams(),
        description="The parameters for the address configuration",
    )


class DNSManagerConfig(BaseConfigSchema):
    enabled: bool = Field(
        default=False, description="Whether the DNS manager is enabled"
    )
    dns: DNSProviderConfig = Field(
        default_factory=DNSProviderConfig, description="The DNS provider configuration"
    )
    managed_sub_domain: str = Field(default="mc", description="The subdomain to manage")

    mc_router_base_url: str = Field(
        default="http://127.0.0.1:26666", description="The base URL for mc-router"
    )

    natmap_monitor: NatmapMonitorConfig = Field(
        default_factory=NatmapMonitorConfig,
        description="The Natmap monitor configuration",
    )
    docker_watcher: DockerWatcherConfig = Field(
        default_factory=DockerWatcherConfig,
        description="The Docker watcher configuration",
    )

    dns_ttl: int = Field(default=15, description="The DNS TTL (Time to Live) value")

    poll_interval: int = Field(
        default=15, description="The polling interval in seconds"
    )

    addresses: list[AddressConfig] = Field(
        default_factory=list, description="The list of address configurations"
    )
