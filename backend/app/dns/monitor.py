import asyncio
from pathlib import Path
from typing import Callable, TypedDict

import aiohttp

from ..logger import logger
from ..minecraft import DockerMCManager
from .mcdns import AddressesT, AddressInfoT

ServersT = dict[str, int]


class MappingValueT(TypedDict):
    ip: str
    port: int


class DockerWatcher:
    def __init__(self, servers_root_path: str | Path) -> None:
        self._servers_root_path = Path(servers_root_path)
        self._docker_mc_manager = DockerMCManager(self._servers_root_path)
        self._previous_servers: ServersT | None = None

    async def get_servers(self) -> ServersT:
        server_info_list = await self._docker_mc_manager.get_all_server_info()
        return {
            server_info.name: server_info.game_port for server_info in server_info_list
        }

    async def watch_servers(self, on_change: Callable[..., None]):
        while True:
            try:
                servers = await self.get_servers()
                if servers != self._previous_servers:
                    if self._previous_servers is not None:
                        on_change()
                    self._previous_servers = servers
            except Exception as e:
                logger.warning(f"error while watching servers: {e}")
            await asyncio.sleep(1)  # Poll interval from config will be used in manager


class NatmapMonitorClient:
    def __init__(self, base_url: str, timeout: int = 5) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        )

        self._timeout = timeout

        self._url = base_url
        if not self._url.endswith("/"):
            self._url += "/"

    async def listen_to_ws(self, on_message: Callable[..., None]):
        """
        should be called in conjunction with asyncio.create_task,
        since it's a infinite loop
        """
        while True:
            try:
                logger.info("connecting to natmap monitor ws...")
                async with self._session.ws_connect(
                    self._url + "ws",
                ) as ws:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            message: dict[str, MappingValueT] = msg.json()
                            # This would need the full config to determine which ports to listen to
                            # For now, we'll just trigger on any message
                            logger.info(f"received natmap message: {message}")
                            on_message()

            except Exception as e:
                logger.warning(f"error while connecting natmap monitor with ws: {e}")
            logger.info("connection to natmap monitor ws closed")
            await asyncio.sleep(self._timeout)

    async def _get_mappings(self) -> dict[str, MappingValueT]:
        async with self._session.get(self._url + "all_mappings") as response:
            return await response.json()

    async def get_addresses_for_config(self, addresses_config: list) -> AddressesT:
        """Get addresses filtered by natmap configuration"""
        mappings = await self._get_mappings()

        addresses = AddressesT()
        for address_config in addresses_config:
            if address_config.get("type") == "natmap":
                port = address_config.get("internal_port", 25565)
                protocol_and_port = f"tcp:{port}"

                if protocol_and_port not in mappings:
                    logger.warning(f"port {port} not found in natmap mappings")
                    continue

                mapping = mappings[protocol_and_port]
                # We would need address_name from config here
                address_name = "*"  # Default, would be configured
                addresses[address_name] = AddressInfoT(
                    type="A",
                    host=mapping["ip"],
                    port=mapping["port"],
                )

        return addresses

    async def close(self):
        """Clean up the session"""
        await self._session.close()
