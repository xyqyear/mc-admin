"""DNS manager: syncs DNS records and MC Router routes against the live server list."""

import asyncio
import hashlib
import json
from typing import Dict, List, Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..dynamic_config import config
from ..logger import logger
from ..minecraft import docker_mc_manager
from .dns import DNSClient
from .dnspod import DNSPodClient
from .huawei import HuaweiDNSClient
from .router import MCRouterClient
from .types import AddRecordT


class AddressInfo(NamedTuple):
    type: Literal["A", "AAAA", "CNAME"]
    host: str
    port: int


class DNSRecord(NamedTuple):
    sub_domain: str
    record_type: str
    value: str
    ttl: int


class RouteEntry(NamedTuple):
    server_address: str
    backend: str


class SimpleDNSManager:
    """Sync DNS records and MC Router routes from ACTIVE Server rows.

    Per-server compose reads are isolated so one drifted row can't poison
    the whole reconciliation tick.
    """

    def __init__(self):
        self._dns_client: DNSClient | None = None
        self._mc_router_client: MCRouterClient | None = None
        self._docker_manager = docker_mc_manager
        self._update_lock = asyncio.Lock()
        self._last_config_hash: str | None = None

    async def initialize(self):
        dns_config = config.dns

        if not dns_config.enabled:
            logger.info("DNS manager is disabled in configuration")
            return

        if dns_config.dns.type == "dnspod":
            self._dns_client = DNSPodClient(
                dns_config.dns.domain,
                dns_config.dns.id,
                dns_config.dns.key,
            )
        elif dns_config.dns.type == "huawei":
            self._dns_client = HuaweiDNSClient(
                dns_config.dns.domain,
                dns_config.dns.ak,
                dns_config.dns.sk,
                dns_config.dns.region,
            )
        else:
            raise ValueError(f"Unsupported DNS provider: {dns_config.dns.type}")

        if not self._dns_client.is_initialized():
            await self._dns_client.init()

        self._mc_router_client = MCRouterClient(dns_config.mc_router_base_url)

        self._last_config_hash = self._calculate_config_hash(dns_config)

        logger.info("Simplified DNS manager initialized successfully")

    def _calculate_config_hash(self, dns_config) -> str:
        """Hash of fields whose changes require reinitializing the DNS/Router clients."""
        key_config = {
            "enabled": dns_config.enabled,
            "dns": dns_config.dns.model_dump() if dns_config.dns else None,
            "mc_router_base_url": dns_config.mc_router_base_url,
        }

        config_str = json.dumps(key_config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    async def _ensure_up_to_date_config(self):
        """Reinitialize clients if relevant config fields changed since last init."""
        dns_config = config.dns
        current_hash = self._calculate_config_hash(dns_config)

        if self._last_config_hash != current_hash:
            logger.info(
                f"DNS configuration changed (hash: {self._last_config_hash} -> {current_hash}), reinitializing..."
            )
            try:
                await self.initialize()
            except Exception as e:
                logger.error(
                    f"Failed to reinitialize DNS manager after config change: {e}"
                )
                raise

            self._last_config_hash = current_hash
            logger.info("DNS manager reinitialized successfully due to config change")

    async def _get_target_records_and_routes(self, db: AsyncSession):
        # Deferred import avoids the app.servers.lifecycle → app.dns cycle.
        from ..servers.crud import get_active_servers


        if self._dns_client is None:
            raise RuntimeError("DNS manager not initialized. Call initialize() first.")

        dns_config = config.dns

        active_rows = await get_active_servers(db)

        async def _read_port(server_id: str) -> int:
            instance = self._docker_manager.get_instance(server_id)
            info = await instance.get_server_info()
            return info.game_port

        port_results = await asyncio.gather(
            *(_read_port(row.server_id) for row in active_rows),
            return_exceptions=True,
        )

        servers: Dict[str, int] = {}
        for row, result in zip(active_rows, port_results):
            if isinstance(result, BaseException):
                logger.warning(
                    f"DNS: skipping server '{row.server_id}' (cannot read compose): {result}"
                )
                continue
            servers[row.server_id] = result

        addresses = self._get_addresses_from_config(dns_config.addresses)

        if not addresses or not servers:
            return None, None, None, None

        target_dns_records = self._generate_dns_records(
            addresses,
            list(servers.keys()),
            dns_config.managed_sub_domain,
            dns_config.dns_ttl,
        )

        target_routes = self._generate_routes(
            addresses,
            servers,
            dns_config.managed_sub_domain,
            self._dns_client.get_domain(),
        )

        return target_dns_records, target_routes, addresses, servers

    async def update(self, db: AsyncSession):
        """Reconcile DNS records and MC Router routes with the current server state."""
        await self._ensure_up_to_date_config()

        if (
            not self._dns_client
            or not self._mc_router_client
            or not self._docker_manager
        ):
            raise RuntimeError("DNS manager not initialized. Call initialize() first.")

        async with self._update_lock:
            logger.info("Starting DNS update...")

            (
                dns_records,
                routes,
                addresses,
                servers,
            ) = await self._get_target_records_and_routes(db)

            if dns_records is None or routes is None:
                logger.warning("No addresses or servers found, skipping DNS update")
                return

            logger.info(
                f"Found {0 if not servers else len(servers)} servers and {0 if not addresses else len(addresses)} addresses"
            )

            try:
                await asyncio.gather(
                    self._update_dns_records(dns_records),
                    self._update_mc_router(routes),
                )
            except Exception as e:
                logger.error(f"Error during DNS update: {e}")
                raise

        logger.info("DNS update completed successfully")

    def _get_addresses_from_config(
        self, addresses_config: list
    ) -> Dict[str, AddressInfo]:
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
        addresses: Dict[str, AddressInfo],
        server_list: List[str],
        managed_sub_domain: str,
        dns_ttl: int,
    ) -> List[DNSRecord]:
        records = []

        for address_name, address_info in addresses.items():
            if address_name == "*":
                sub_domain_base = managed_sub_domain
            else:
                sub_domain_base = f"{address_name}.{managed_sub_domain}"

            records.append(
                DNSRecord(
                    sub_domain=f"*.{sub_domain_base}",
                    record_type=address_info.type,
                    value=address_info.host,
                    ttl=dns_ttl,
                )
            )

            for server_name in server_list:
                domain = (
                    self._dns_client.get_domain() if self._dns_client else "localhost"
                )
                srv_value = (
                    f"0 5 {address_info.port} {server_name}.{sub_domain_base}.{domain}"
                )
                records.append(
                    DNSRecord(
                        sub_domain=f"_minecraft._tcp.{server_name}.{sub_domain_base}",
                        record_type="SRV",
                        value=srv_value,
                        ttl=dns_ttl,
                    )
                )

        return records

    def _generate_routes(
        self,
        addresses: Dict[str, AddressInfo],
        servers: Dict[str, int],
        managed_sub_domain: str,
        domain: str,
    ) -> List[RouteEntry]:
        routes = []

        for server_name, server_port in servers.items():
            for address_name in addresses.keys():
                if address_name == "*":
                    sub_domain_base = managed_sub_domain
                else:
                    sub_domain_base = f"{address_name}.{managed_sub_domain}"

                server_address = f"{server_name}.{sub_domain_base}.{domain}"
                backend = f"localhost:{server_port}"

                routes.append(
                    RouteEntry(server_address=server_address, backend=backend)
                )

        return routes

    async def _update_dns_records(self, target_records: List[DNSRecord]):
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

        # Pass managed_sub_domain so the DNS client only diffs records under our scope.
        dns_config = config.dns
        await self._dns_client.update_records(
            target_add_records, dns_config.managed_sub_domain
        )

    async def _update_mc_router(self, target_routes: List[RouteEntry]):
        if not self._mc_router_client:
            return

        routes_dict = {route.server_address: route.backend for route in target_routes}

        logger.info(f"Updating MC Router with {len(routes_dict)} routes")
        await self._mc_router_client.override_routes(routes_dict)

    async def close(self):
        if self._mc_router_client:
            await self._mc_router_client.close()

    async def get_current_diff(self, db: AsyncSession):
        """Compute the pending changes against DNS provider and MC Router for UI display."""
        await self._ensure_up_to_date_config()

        if (
            not self._dns_client
            or not self._mc_router_client
            or not self._docker_manager
        ):
            raise RuntimeError("DNS manager not initialized")

        dns_config = config.dns

        (
            target_dns_records,
            target_routes,
            _,
            _,
        ) = await self._get_target_records_and_routes(db)

        if target_dns_records is None or target_routes is None:
            raise ValueError("No addresses or servers found for diff calculation")

        target_add_records = [
            AddRecordT(
                sub_domain=record.sub_domain,
                value=record.value,
                record_type=record.record_type,
                ttl=record.ttl,
            )
            for record in target_dns_records
        ]
        dns_diff = await self._dns_client.get_records_diff(
            target_add_records, dns_config.managed_sub_domain
        )

        target_routes_dict = {
            route.server_address: route.backend for route in target_routes
        }
        router_diff = await self._mc_router_client.get_routes_diff(target_routes_dict)

        return dns_diff, router_diff

    @property
    def is_initialized(self) -> bool:
        return (
            self._dns_client is not None
            and self._mc_router_client is not None
            and self._docker_manager is not None
        )


simple_dns_manager = SimpleDNSManager()
