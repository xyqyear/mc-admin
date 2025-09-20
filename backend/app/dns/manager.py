"""
Main DNS Manager that coordinates DNS, Router, and Server monitoring.

This class integrates all components to automatically manage DNS records and
router configurations based on Minecraft server status.
"""

import asyncio
from typing import NamedTuple, Optional

from ..config import settings
from ..dynamic_config import config
from ..logger import logger
from .dnspod import DNSPodClient
from .huawei import HuaweiDNSClient
from .mcdns import MCDNS, AddressesT, AddressInfoT
from .monitor import DockerWatcher, NatmapMonitorClient, ServersT
from .router import MCRouter, MCRouterClient


class PullResultT(NamedTuple):
    addresses: AddressesT
    servers: ServersT


class Local:
    """Handles local server and network monitoring"""

    def __init__(
        self,
        docker_watcher: DockerWatcher,
        natmap_monitor_client: Optional[NatmapMonitorClient],
        addresses_config: list,
    ) -> None:
        self._docker_watcher = docker_watcher
        self._natmap_monitor_client = natmap_monitor_client
        self._addresses_config = addresses_config

    async def pull(self) -> PullResultT:
        """Pull current local state (servers and addresses)"""
        addresses = AddressesT()

        # Process configured addresses
        for addr_config in self._addresses_config:
            address_name = addr_config.name
            if addr_config.type == "natmap":
                # Handle natmap addresses
                if self._natmap_monitor_client:
                    try:
                        mappings = await self._natmap_monitor_client._get_mappings()
                        protocol_and_port = f"tcp:{addr_config.internal_port}"
                        if protocol_and_port in mappings:
                            mapping = mappings[protocol_and_port]
                            addresses[address_name] = AddressInfoT(
                                type="A",
                                host=mapping["ip"],
                                port=mapping["port"],
                            )
                        else:
                            logger.warning(
                                f"Port {addr_config.internal_port} not found in natmap mappings"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to get natmap mapping for {address_name}: {e}"
                        )
            elif addr_config.type == "manual":
                # Handle manual addresses
                addresses[address_name] = AddressInfoT(
                    type=addr_config.record_type,
                    host=addr_config.value,
                    port=addr_config.port,
                )

        # Get servers from Docker watcher
        servers = await self._docker_watcher.get_servers()

        return PullResultT(addresses=addresses, servers=servers)


class Remote:
    """Handles remote DNS and router state management"""

    def __init__(self, mc_router: MCRouter, mc_dns: MCDNS) -> None:
        self._mc_router = mc_router
        self._mc_dns = mc_dns

    async def push(self, addresses: AddressesT, servers: ServersT):
        """Push state to both router and DNS"""
        await asyncio.gather(
            self._mc_router.push(list(addresses.keys()), servers),
            self._mc_dns.push(addresses, list(servers.keys())),
        )

    async def pull(self) -> Optional[PullResultT]:
        """
        Pull current remote state (router and DNS)
        Returns None if DNS/router state is inconsistent
        """
        (address_list, servers), mcdns_pull_result = await asyncio.gather(
            self._mc_router.pull(), self._mc_dns.pull()
        )

        if not mcdns_pull_result:
            return None

        addresses, server_list = mcdns_pull_result

        # Check consistency between router and DNS
        if set(address_list) != set(addresses.keys()):
            return None

        if set(server_list) != set(servers.keys()):
            return None

        return PullResultT(addresses, servers)


class DNSManager:
    """
    Main DNS manager that coordinates all components.

    This class monitors local server state and automatically updates
    DNS records and router configurations to keep everything in sync.
    """

    def __init__(self):
        self._background_tasks: list[asyncio.Task] = []
        self._running = False

        # Components will be initialized in start()
        self._mcdns: Optional[MCDNS] = None
        self._mcrouter: Optional[MCRouter] = None
        self._docker_watcher: Optional[DockerWatcher] = None
        self._natmap_monitor: Optional[NatmapMonitorClient] = None
        self._local: Optional[Local] = None
        self._remote: Optional[Remote] = None

        # Control variables
        self._update_queue = 0
        self._update_lock = asyncio.Lock()
        self._backoff_timer = 2

    def _queue_update(self):
        """Queue an update due to a detected change"""
        logger.info("queueing update")
        self._update_queue += 1

    async def _update(self):
        """
        Check for updates and apply them if necessary
        :return: True if updated, False otherwise
        """
        if not self._remote or not self._local:
            return False

        logger.debug("checking for updates...")
        remote_pull_result, local_pull_result = await asyncio.gather(
            self._remote.pull(), self._local.pull()
        )

        if remote_pull_result == local_pull_result:
            return False

        logger.info(f"pushing changes: {local_pull_result}")
        await self._remote.push(local_pull_result.addresses, local_pull_result.servers)
        return True

    async def _try_update(self):
        """Try to update with backoff on errors"""
        await asyncio.sleep(self._backoff_timer - 2)
        try:
            async with self._update_lock:
                if await self._update():
                    # wait for DNS provider to update
                    await asyncio.sleep(10)
            # reset backoff timer if successful
            self._backoff_timer = 2
        except Exception as e:
            logger.warning(f"error while updating: {e}")
            # set a maximum backoff timer of 60 seconds
            if self._backoff_timer < 60:
                self._backoff_timer *= 1.5

    async def _check_queue_loop(self):
        """Process update queue"""
        while self._running:
            if self._update_queue > 0:
                self._update_queue -= 1
                await self._try_update()
            await asyncio.sleep(1)

    async def _polling_loop(self):
        """Main polling loop"""
        while self._running:
            poll_interval = config.dns.poll_interval
            await asyncio.sleep(poll_interval)
            await self._try_update()

    async def start(self):
        """Start the DNS manager"""
        if self._running:
            logger.warning("DNS manager already running")
            return

        dns_config = config.dns

        if not dns_config.enabled:
            logger.info("DNS manager is disabled in configuration")
            return

        logger.info("Starting DNS manager...")

        try:
            # Initialize DNS client based on configuration
            if dns_config.dns.type == "dnspod":
                dns_client = DNSPodClient(
                    dns_config.dns.domain,
                    dns_config.dns.id,
                    dns_config.dns.key,
                )
            elif dns_config.dns.type == "huawei":
                dns_client = HuaweiDNSClient(
                    dns_config.dns.domain,
                    dns_config.dns.ak,
                    dns_config.dns.sk,
                    dns_config.dns.region,
                )
            else:
                raise ValueError(f"Unsupported DNS provider: {dns_config.dns.type}")

            # Initialize MCDNS
            self._mcdns = MCDNS(
                dns_client, dns_config.managed_sub_domain, dns_config.dns_ttl
            )

            # Initialize MC Router client
            mcrouter_client = MCRouterClient(dns_config.mc_router_base_url)
            self._mcrouter = MCRouter(
                mcrouter_client,
                dns_client.get_domain(),
                dns_config.managed_sub_domain,
            )

            # Initialize Docker watcher
            self._docker_watcher = DockerWatcher(settings.server_path)

            # Initialize Natmap monitor if enabled
            if dns_config.natmap_monitor.enabled:
                self._natmap_monitor = NatmapMonitorClient(
                    dns_config.natmap_monitor.base_url
                )
            else:
                self._natmap_monitor = None

            # Initialize local and remote managers
            self._local = Local(
                self._docker_watcher, self._natmap_monitor, dns_config.addresses
            )
            self._remote = Remote(self._mcrouter, self._mcdns)

            # Run initial update
            logger.info("running initial check...")
            while True:
                try:
                    await self._update()
                    break
                except Exception as e:
                    logger.warning(f"error while initializing: {e}")
                    await asyncio.sleep(self._backoff_timer - 2)
                    self._backoff_timer *= 1.5
            self._backoff_timer = 2
            logger.info("initial check done.")

            # Start monitoring tasks
            self._running = True

            # Start background tasks
            self._background_tasks = []
            if self._docker_watcher:
                self._background_tasks.append(
                    asyncio.create_task(
                        self._docker_watcher.watch_servers(self._queue_update)
                    )
                )
            self._background_tasks.append(asyncio.create_task(self._check_queue_loop()))
            self._background_tasks.append(asyncio.create_task(self._polling_loop()))

            if self._natmap_monitor:
                self._background_tasks.append(
                    asyncio.create_task(
                        self._natmap_monitor.listen_to_ws(self._queue_update)
                    )
                )

            logger.info("DNS manager started successfully")

        except Exception as e:
            logger.error(f"Failed to start DNS manager: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop the DNS manager"""
        if not self._running:
            return

        logger.info("Stopping DNS manager...")
        self._running = False

        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete or be cancelled
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()

        # Clean up resources
        if self._natmap_monitor:
            await self._natmap_monitor.close()

        # Clean up router client session
        if self._mcrouter and hasattr(self._mcrouter, "_client"):
            await self._mcrouter._client.close()

        logger.info("DNS manager stopped")

    @property
    def is_running(self) -> bool:
        """Check if the DNS manager is running"""
        return self._running


# Global DNS manager instance
dns_manager = DNSManager()
