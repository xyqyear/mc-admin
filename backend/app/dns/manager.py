"""
Simplified DNS Manager

A lightweight DNS management system that directly integrates with DockerMCManager
to synchronize DNS records and MC Router configurations without background tasks.
"""

import asyncio
import hashlib
import json
from typing import Dict, List, Literal, NamedTuple

from ..config import settings
from ..dynamic_config import config
from ..logger import logger
from ..minecraft import DockerMCManager
from .dns import DNSClient
from .dnspod import DNSPodClient
from .huawei import HuaweiDNSClient
from .router import MCRouterClient
from .types import AddRecordT


class AddressInfo(NamedTuple):
    """Address information for DNS records"""

    type: Literal["A", "AAAA", "CNAME"]
    host: str
    port: int


class DNSRecord(NamedTuple):
    """Abstract DNS record representation"""

    sub_domain: str
    record_type: str
    value: str
    ttl: int


class RouteEntry(NamedTuple):
    """MC Router route entry"""

    server_address: str
    backend: str


class SimpleDNSManager:
    """
    Simplified DNS manager that provides a single update() API.

    This manager:
    1. Uses DockerMCManager to get current server list and ports
    2. Combines with configuration to generate DNS records and routes
    3. Updates DNS client and MC Router with complete record/route lists
    """

    def __init__(self):
        self._dns_client: DNSClient | None = None
        self._mc_router_client: MCRouterClient | None = None
        self._docker_manager: DockerMCManager | None = None
        self._update_lock = asyncio.Lock()
        self._last_config_hash: str | None = None

    async def initialize(self):
        """Initialize the DNS manager with current configuration"""
        dns_config = config.dns

        if not dns_config.enabled:
            logger.info("DNS manager is disabled in configuration")
            return

        # Initialize DNS client
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

        # Initialize DNS client
        if not self._dns_client.is_initialized():
            await self._dns_client.init()

        # Initialize MC Router client
        self._mc_router_client = MCRouterClient(dns_config.mc_router_base_url)

        # Initialize Docker manager
        self._docker_manager = DockerMCManager(settings.server_path)

        # Update configuration hash to current state
        self._last_config_hash = self._calculate_config_hash(dns_config)

        logger.info("Simplified DNS manager initialized successfully")

    def _calculate_config_hash(self, dns_config) -> str:
        """
        Calculate hash of key configuration fields that affect client initialization.

        Only includes configuration fields that would require reinitializing
        DNS or MC Router clients if changed.

        Args:
            dns_config: DNS configuration object

        Returns:
            MD5 hash of key configuration fields
        """
        key_config = {
            "enabled": dns_config.enabled,
            "dns": dns_config.dns.model_dump() if dns_config.dns else None,
            "mc_router_base_url": dns_config.mc_router_base_url,
        }

        # Use sorted JSON to ensure consistent hash calculation
        config_str = json.dumps(key_config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    async def _ensure_up_to_date_config(self):
        """
        Ensure DNS manager is using the latest configuration.

        Checks if key configuration fields have changed since last initialization
        and automatically reinitializes clients if needed. This enables dynamic
        configuration updates without manual intervention.

        Raises:
            Exception: If reinitialization fails
        """
        dns_config = config.dns
        current_hash = self._calculate_config_hash(dns_config)

        if self._last_config_hash != current_hash:
            logger.info(
                f"DNS configuration changed (hash: {self._last_config_hash} -> {current_hash}), reinitializing..."
            )
            try:
                await self.initialize()
                self._last_config_hash = current_hash
                logger.info("DNS manager reinitialized successfully due to config change")
            except Exception as e:
                logger.error(f"Failed to reinitialize DNS manager after config change: {e}")
                raise

    async def update(self):
        """
        Update DNS records and MC Router configurations based on current server state.

        This method:
        1. Ensures configuration is up-to-date (auto-reinitializes if config changed)
        2. Gets server list and ports from DockerMCManager
        3. Combines with address configuration to generate records
        4. Updates DNS and MC Router with complete lists
        """
        # Ensure we're using the latest configuration
        await self._ensure_up_to_date_config()

        if (
            not self._dns_client
            or not self._mc_router_client
            or not self._docker_manager
        ):
            raise RuntimeError("DNS manager not initialized. Call initialize() first.")

        async with self._update_lock:
            logger.info("Starting DNS update...")

            dns_config = config.dns

            try:
                # Get current server information
                server_info_list = await self._docker_manager.get_all_server_info()
                servers = {info.name: info.game_port for info in server_info_list}

                # Get addresses from configuration
                addresses = await self._get_addresses_from_config(dns_config.addresses)

                if not addresses or not servers:
                    logger.warning("No addresses or servers found, skipping DNS update")
                    return

                logger.info(
                    f"Found {len(servers)} servers and {len(addresses)} addresses"
                )

                # Generate DNS records and routes
                dns_records = self._generate_dns_records(
                    addresses,
                    list(servers.keys()),
                    dns_config.managed_sub_domain,
                    dns_config.dns_ttl,
                )

                routes = self._generate_routes(
                    addresses,
                    servers,
                    dns_config.managed_sub_domain,
                    self._dns_client.get_domain(),
                )

                # Update DNS and MC Router in parallel
                await asyncio.gather(
                    self._update_dns_records(dns_records),
                    self._update_mc_router(routes),
                )

                logger.info("DNS update completed successfully")

            except Exception as e:
                logger.error(f"Error during DNS update: {e}")
                raise

    async def _get_addresses_from_config(
        self, addresses_config: list
    ) -> Dict[str, AddressInfo]:
        """Extract addresses from configuration"""
        addresses = {}

        for addr_config in addresses_config:
            if addr_config.type == "manual":
                addresses[addr_config.name] = AddressInfo(
                    type=addr_config.record_type,
                    host=addr_config.value,
                    port=addr_config.port,
                )
            elif addr_config.type == "natmap":
                # For natmap, we would need to query the natmap service
                # For now, skip natmap addresses in the simplified implementation
                logger.warning(
                    f"Natmap address {addr_config.name} skipped - not implemented in simplified manager"
                )
                continue

        return addresses

    def _generate_dns_records(
        self,
        addresses: Dict[str, AddressInfo],
        server_list: List[str],
        managed_sub_domain: str,
        dns_ttl: int,
    ) -> List[DNSRecord]:
        """Generate complete list of DNS records"""
        records = []

        for address_name, address_info in addresses.items():
            # Generate base address record (A/AAAA/CNAME)
            if address_name == "*":
                sub_domain_base = managed_sub_domain
            else:
                sub_domain_base = f"{address_name}.{managed_sub_domain}"

            # Wildcard record for this address
            records.append(
                DNSRecord(
                    sub_domain=f"*.{sub_domain_base}",
                    record_type=address_info.type,
                    value=address_info.host,
                    ttl=dns_ttl,
                )
            )

            # SRV records for each server
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
        """Generate complete list of MC Router routes"""
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
        """Update DNS records to match target state"""
        if not self._dns_client:
            return

        # Convert target records to the format expected by DNS client
        target_add_records = [
            AddRecordT(
                sub_domain=record.sub_domain,
                value=record.value,
                record_type=record.record_type,
                ttl=record.ttl,
            )
            for record in target_records
        ]

        # Let the DNS client handle the diffing and updates
        # Pass managed_sub_domain to ensure only relevant records are updated
        dns_config = config.dns
        await self._dns_client.update_records(target_add_records, dns_config.managed_sub_domain)

    async def _update_mc_router(self, target_routes: List[RouteEntry]):
        """Update MC Router with target routes"""
        if not self._mc_router_client:
            return

        # Convert to the format expected by MC Router client
        routes_dict = {route.server_address: route.backend for route in target_routes}

        logger.info(f"Updating MC Router with {len(routes_dict)} routes")
        await self._mc_router_client.override_routes(routes_dict)


    async def close(self):
        """Clean up resources"""
        if self._mc_router_client:
            await self._mc_router_client.close()

    async def get_current_diff(self):
        """
        Get the current differences between expected and actual DNS/Router state.

        Returns a dictionary containing:
        - dns_diff: RecordDiff with DNS record differences
        - router_diff: Dict with router route differences
        - errors: List of any errors encountered during diff calculation

        This is useful for status checks and UI display of pending changes.
        """
        # Ensure we're using the latest configuration
        await self._ensure_up_to_date_config()

        if (
            not self._dns_client
            or not self._mc_router_client
            or not self._docker_manager
        ):
            return {
                "dns_diff": None,
                "router_diff": None,
                "errors": ["DNS manager not initialized"]
            }

        errors = []
        dns_diff = None
        router_diff = None

        try:
            dns_config = config.dns

            # Get current server information
            server_info_list = await self._docker_manager.get_all_server_info()
            servers = {info.name: info.game_port for info in server_info_list}

            # Get addresses from configuration
            addresses = await self._get_addresses_from_config(dns_config.addresses)

            if not addresses or not servers:
                return {
                    "dns_diff": None,
                    "router_diff": None,
                    "errors": ["No addresses or servers found for diff calculation"]
                }

            # Generate target DNS records and routes
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

            # Calculate DNS diff
            try:
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
                    target_add_records,
                    dns_config.managed_sub_domain
                )
            except Exception as e:
                errors.append(f"DNS diff calculation failed: {str(e)}")

            # Calculate Router diff
            try:
                target_routes_dict = {route.server_address: route.backend for route in target_routes}
                router_diff = await self._mc_router_client.get_routes_diff(target_routes_dict)
            except Exception as e:
                errors.append(f"Router diff calculation failed: {str(e)}")

        except Exception as e:
            errors.append(f"General diff calculation failed: {str(e)}")

        return {
            "dns_diff": dns_diff,
            "router_diff": router_diff,
            "errors": errors
        }

    @property
    def is_initialized(self) -> bool:
        """Check if the manager is initialized"""
        return (
            self._dns_client is not None
            and self._mc_router_client is not None
            and self._docker_manager is not None
        )


# Global instance
simple_dns_manager = SimpleDNSManager()
