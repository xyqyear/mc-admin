"""DNS manager: syncs DNS records and MC Router routes against the live server list."""

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from ..dynamic_config import get_config
from ..dynamic_config.configs.dns import DNSManagerConfig
from ..errors import PublicOperationError, log_safe_error
from ..logger import get_logger
from ..minecraft import DockerMCManager, get_docker_mc_manager
from ..operations.finalization import finalize
from ..runtime_resources import current_runtime
from .dns import DNSClient
from .dnspod import DNSPodClient
from .huawei import HuaweiDNSClient
from .planning import (
    AddressInfo,
    ConnectivityObservation,
    DesiredConnectivity,
    DNSRecord,
    RouteDiff,
    RouteEntry,
    diff_routes,
    generate_dns_records,
    generate_routes,
)
from .router import MCRouterClient
from .types import AddRecordT, RecordListT
from .utils import RecordDiff, diff_dns_records


class SimpleDNSManager:
    """Sync DNS records and MC Router routes from ACTIVE Server rows.

    Per-server compose reads are isolated so one drifted row can't poison
    the whole reconciliation tick.
    """

    def __init__(self, *, configuration: Callable[[], DNSManagerConfig] | None = None, docker_manager: DockerMCManager | None = None):
        self._configuration = configuration if configuration is not None else lambda: get_config().dns
        self._dns_client: DNSClient | None = None
        self._mc_router_client: MCRouterClient | None = None
        self._docker_manager = docker_manager if docker_manager is not None else get_docker_mc_manager()
        self._update_lock = asyncio.Lock()
        self._last_config_hash: str | None = None
        self._unknown_servers: tuple[str, ...] = ()
        self._last_apply_issues: tuple[str, ...] = ()
        self._owned_clients: list[DNSClient | MCRouterClient] = []

    async def initialize(self, dns_config: DNSManagerConfig | None = None):
        async with self._update_lock:
            dns_config = dns_config if dns_config is not None else self._configuration()
            await self._ensure_up_to_date_config(dns_config)

    async def _initialize(self, dns_config: DNSManagerConfig):

        if not dns_config.enabled:
            previous_dns = self._dns_client
            previous_router = self._mc_router_client
            self._dns_client = None
            self._mc_router_client = None
            self._last_config_hash = self._calculate_config_hash(dns_config)
            await self._close_clients(previous_dns, previous_router)
            get_logger().info("DNS manager is disabled in configuration")
            return

        router_client = MCRouterClient(dns_config.mc_router_base_url)
        self._owned_clients.append(router_client)
        dns_client: DNSClient | None = None
        try:
            if dns_config.dns.type == "dnspod":
                dns_client = DNSPodClient(dns_config.dns.domain, dns_config.dns.id, dns_config.dns.key)
            elif dns_config.dns.type == "huawei":
                dns_client = HuaweiDNSClient(dns_config.dns.domain, dns_config.dns.ak, dns_config.dns.sk, dns_config.dns.region)
            else:
                raise ValueError(f"Unsupported DNS provider: {dns_config.dns.type}")
            self._owned_clients.append(dns_client)
            if not dns_client.is_initialized():
                await dns_client.init()
        except Exception as exc:  # noqa: BLE001 - The router remains available when the provider fails.
            log_safe_error(exc, "DNS provider initialization failed")
            if dns_client is not None:
                try:
                    await self._close_clients(dns_client)
                except BaseException:
                    await self._close_clients(router_client)
                    raise
            dns_client = None
        except BaseException:
            await self._close_clients(dns_client, router_client)
            raise
        previous_dns = self._dns_client
        previous_router = self._mc_router_client
        self._dns_client = dns_client
        self._mc_router_client = router_client

        self._last_config_hash = self._calculate_config_hash(dns_config)
        await self._close_clients(previous_dns, previous_router)

        if dns_client is not None:
            get_logger().info("DNS provider and MC Router clients ready")
        else:
            get_logger().warning("DNS provider unavailable; MC Router client remains available")

    def _calculate_config_hash(self, dns_config) -> str:
        """Hash of fields whose changes require reinitializing the DNS/Router clients."""
        key_config = {
            "enabled": dns_config.enabled,
            "dns": dns_config.dns.model_dump() if dns_config.dns else None,
            "mc_router_base_url": dns_config.mc_router_base_url,
        }

        config_str = json.dumps(key_config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    async def _ensure_up_to_date_config(self, dns_config: DNSManagerConfig | None = None):
        """Reinitialize clients if relevant config fields changed since last init."""
        dns_config = dns_config if dns_config is not None else self._configuration()
        current_hash = self._calculate_config_hash(dns_config)

        if self._last_config_hash != current_hash or (dns_config.enabled and self._dns_client is None):
            get_logger().info(
                f"DNS configuration changed (hash: {self._last_config_hash} -> {current_hash}), reinitializing..."
            )
            try:
                await self._initialize(dns_config)
            except Exception as exc:
                log_safe_error(exc, "DNS client refresh failed")
                raise

            self._last_config_hash = current_hash
            get_logger().info("DNS client configuration refreshed")

    async def _get_target_records_and_routes(
        self, db: AsyncSession, dns_config: DNSManagerConfig | None = None
    ):
        # Deferred import avoids the app.servers.lifecycle → app.dns cycle.
        from ..servers.crud import get_active_servers


        dns_config = dns_config if dns_config is not None else self._configuration()

        active_rows = await get_active_servers(db)

        async def _read_port(server_id: str) -> int:
            instance = self._docker_manager.get_instance(server_id)
            info = await instance.get_server_info()
            return info.game_port

        port_results = await asyncio.gather(
            *(_read_port(row.server_id) for row in active_rows),
            return_exceptions=True,
        )

        servers: dict[str, int] = {}
        unknown_servers: list[str] = []
        for row, result in zip(active_rows, port_results):
            if isinstance(result, BaseException):
                unknown_servers.append(row.server_id)
                if isinstance(result, Exception):
                    log_safe_error(result, f"DNS cannot read server {row.server_id}")
                continue
            servers[row.server_id] = result

        self._unknown_servers = tuple(unknown_servers)
        addresses = self._get_addresses_from_config(dns_config.addresses)

        if not addresses or not servers:
            return None, None, None, None

        target_dns_records = self._generate_dns_records(
            addresses,
            list(servers.keys()),
            dns_config.managed_sub_domain,
            dns_config.dns_ttl,
            self._dns_client.get_domain() if self._dns_client is not None else dns_config.dns.domain,
        )

        target_routes = self._generate_routes(
            addresses,
            servers,
            dns_config.managed_sub_domain,
            self._dns_client.get_domain() if self._dns_client is not None else dns_config.dns.domain,
        )

        return target_dns_records, target_routes, addresses, servers

    async def update(self, db: AsyncSession):
        """Apply a fresh known plan; unknown observations never authorize deletion."""
        async with self._update_lock:
            dns_config = self._configuration()
            await self._ensure_up_to_date_config(dns_config)
            if not dns_config.enabled:
                return
            self._last_apply_issues = ()
            observed = await self._observe(db, dns_config)
            if observed.empty_desired and not observed.unknown_servers:
                return observed

            async def apply() -> None:
                jobs = []
                labels = []
                if observed.dns_diff is not None and self._dns_client is not None:
                    jobs.append(self._dns_client.apply_diff(observed.dns_diff))
                    labels.append("DNS 记录更新未完成，请重试")
                if observed.router_diff is not None and self._mc_router_client is not None:
                    jobs.append(self._mc_router_client.apply_diff(observed.router_diff))
                    labels.append("MC Router 路由更新未完成，请重试")
                results = await asyncio.gather(*jobs, return_exceptions=True)
                issues = []
                for label, result in zip(labels, results):
                    if isinstance(result, BaseException):
                        issues.append(label)
                        if isinstance(result, Exception):
                            log_safe_error(result, label)
                self._last_apply_issues = tuple(issues)

            await finalize(apply())
            if observed.issues or self._last_apply_issues:
                raise PublicOperationError("部分网络配置未完成，请查看 DNS 状态后重试")
            return observed

    async def observe(self, db: AsyncSession) -> ConnectivityObservation:
        async with self._update_lock:
            dns_config = self._configuration()
            await self._ensure_up_to_date_config(dns_config)
            return await self._observe(db, dns_config)

    async def _observe(self, db: AsyncSession, dns_config: DNSManagerConfig) -> ConnectivityObservation:
        self._unknown_servers = ()
        try:
            records, routes, _, _ = await self._get_target_records_and_routes(db, dns_config)
        except Exception as exc:  # noqa: BLE001 - Unknown server inventory cannot authorize writes.
            log_safe_error(exc, "DNS server inventory observation failed")
            return ConnectivityObservation(None, None, issues=("服务器列表状态未知，已保留现有网络配置，请稍后重试",))
        target_records = [AddRecordT(record.sub_domain, record.value, record.record_type, record.ttl) for record in records or []]
        desired = DesiredConnectivity(tuple(target_records), tuple(routes or []), self._unknown_servers)
        empty = desired.empty
        target_routes = {route.server_address: route.backend for route in desired.routes}
        issues = []
        if self._unknown_servers:
            issues.append("部分服务器配置无法读取，已保留现有记录并暂停删除，请修复后重试")

        async def dns_observation() -> RecordDiff | None:
            try:
                if self._dns_client is None:
                    raise RuntimeError("DNS provider unavailable")
                current = await self._dns_client.list_relevant_records(dns_config.managed_sub_domain)
                if empty:
                    return RecordDiff([], [], [])
                diff = diff_dns_records(current, target_records)
                return diff if desired.allow_removals else diff._replace(records_to_remove=[])
            except Exception as exc:  # noqa: BLE001 - Failed observations must remain unknown.
                log_safe_error(exc, "DNS record observation failed")
                issues.append("DNS 记录状态未知，已保留现有记录，请检查服务商配置后重试")
                return None

        async def router_observation() -> RouteDiff | None:
            try:
                if self._mc_router_client is None:
                    raise RuntimeError("MC Router unavailable")
                current = await self._mc_router_client.get_routes()
                return diff_routes(current, current if empty else target_routes, allow_removals=desired.allow_removals)
            except Exception as exc:  # noqa: BLE001 - Failed observations must remain unknown.
                log_safe_error(exc, "MC Router observation failed")
                issues.append("MC Router 状态未知，已保留现有路由，请检查连接后重试")
                return None

        dns_diff, router_diff = await asyncio.gather(dns_observation(), router_observation())
        observed = ConnectivityObservation(dns_diff, router_diff, self._unknown_servers, tuple(issues), empty)
        if observed.state == "ready":
            self._last_apply_issues = ()
        elif self._last_apply_issues:
            observed = replace(observed, issues=(*observed.issues, *self._last_apply_issues))
        return observed

    def _get_addresses_from_config(
        self, addresses_config: list
    ) -> dict[str, AddressInfo]:
        addresses = {}

        for addr_config in addresses_config:
            if addr_config.type == "manual":
                addresses[addr_config.name] = AddressInfo(
                    type=addr_config.record_type,
                    host=addr_config.value,
                    port=addr_config.port,
                )

        return addresses

    def _generate_dns_records(
        self,
        addresses: dict[str, AddressInfo],
        server_list: list[str],
        managed_sub_domain: str,
        dns_ttl: int,
        domain: str | None = None,
    ) -> list[DNSRecord]:
        domain = domain if domain is not None else (self._dns_client.get_domain() if self._dns_client is not None else self._configuration().dns.domain)
        return generate_dns_records(addresses, server_list, managed_sub_domain, dns_ttl, domain)

    def _generate_routes(
        self,
        addresses: dict[str, AddressInfo],
        servers: dict[str, int],
        managed_sub_domain: str,
        domain: str,
    ) -> list[RouteEntry]:
        return generate_routes(addresses, servers, managed_sub_domain, domain)

    async def _update_dns_records(
        self, target_records: list[DNSRecord], managed_sub_domain: str
    ):
        if not self._dns_client:
            return

        target_add_records = [
            AddRecordT(
                sub_domain=record.sub_domain,
                value=record.value,
                record_type=record.record_type,
                ttl=record.ttl,
            )
            for record in target_records
        ]

        await self._dns_client.update_records(
            target_add_records, managed_sub_domain
        )

    async def _update_mc_router(self, target_routes: list[RouteEntry]):
        if not self._mc_router_client:
            return

        routes_dict = {route.server_address: route.backend for route in target_routes}

        get_logger().info(f"Updating MC Router with {len(routes_dict)} routes")
        await self._mc_router_client.override_routes(routes_dict)

    async def close(self):
        async with self._update_lock:
            clients = [*self._owned_clients, self._dns_client, self._mc_router_client]
            self._dns_client = None
            self._mc_router_client = None
            self._last_config_hash = None
            await self._close_clients(*clients)

    async def _close_clients(self, *clients: DNSClient | MCRouterClient | None) -> None:
        unique = {id(client): client for client in clients if client is not None}
        results = await finalize(asyncio.gather(
            *(client.close() for client in unique.values()), return_exceptions=True,
        ))
        errors = []
        for client, result in zip(unique.values(), results):
            if isinstance(result, BaseException):
                if not any(owned is client for owned in self._owned_clients):
                    self._owned_clients.append(client)
                errors.append(result)
            else:
                self._owned_clients = [owned for owned in self._owned_clients if owned is not client]
        if errors:
            raise BaseExceptionGroup("DNS 客户端关闭失败", errors)

    async def get_dns_records(self) -> RecordListT:
        async with self._update_lock:
            dns_config = self._configuration()
            await self._ensure_up_to_date_config(dns_config)
            if self._dns_client is None:
                raise RuntimeError("DNS manager not initialized")
            return await self._dns_client.list_relevant_records(
                dns_config.managed_sub_domain
            )

    async def get_router_routes(self) -> dict[str, str]:
        async with self._update_lock:
            dns_config = self._configuration()
            await self._ensure_up_to_date_config(dns_config)
            if self._mc_router_client is None:
                raise RuntimeError("DNS manager not initialized")
            return await self._mc_router_client.get_routes()

    async def get_current_diff(self, db: AsyncSession):
        """Compute the pending changes against DNS provider and MC Router for UI display."""
        async with self._update_lock:
            dns_config = self._configuration()
            await self._ensure_up_to_date_config(dns_config)
            return await self._get_current_diff(db, dns_config)

    async def _get_current_diff(self, db: AsyncSession, dns_config: DNSManagerConfig):
        if not self.is_initialized:
            raise RuntimeError("DNS manager not initialized")
        observed = await self._observe(db, dns_config)
        if observed.empty_desired:
            raise ValueError("No addresses or servers found for diff calculation")
        if observed.dns_diff is None or observed.router_diff is None:
            raise PublicOperationError("网络状态未知，请检查连接后重试")
        return observed.dns_diff, observed.router_diff.as_dict()

    @property
    def is_initialized(self) -> bool:
        return (
            self._dns_client is not None
            and self._mc_router_client is not None
            and self._docker_manager is not None
        )


def get_dns_manager() -> SimpleDNSManager:
    return cast(SimpleDNSManager, current_runtime().resource("dns_manager"))
