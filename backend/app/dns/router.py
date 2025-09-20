"""
wrapper for mc-router client
"""

import asyncio
import json as jsonlib
from typing import (
    Awaitable,
    Literal,
    NamedTuple,
    NotRequired,
    Optional,
    TypedDict,
    cast,
)

import aiohttp

from ..logger import logger

AddressNameListT = list[str]

# server_list: [server_name, server_port]
ServersT = dict[str, int]


class ParsedServerAddressT(NamedTuple):
    server_name: str
    address_name: str
    server_port: int


class MCRouterPullResultT(NamedTuple):
    address_name_list: AddressNameListT
    servers: ServersT


class RoutePoseDataT(TypedDict):
    serverAddress: str
    backend: str


HeadersT = TypedDict(
    "HeadersT", {"Accept": NotRequired[str], "Content-Type": NotRequired[str]}
)


RoutesT = dict[str, str]


class BaseMCRouterClient:
    def __init__(self, base_url: str): ...

    async def get_routes(self) -> RoutesT: ...

    async def override_routes(self, routes: RoutesT): ...

    async def close(self): ...


class MCRouterClient(BaseMCRouterClient):
    def __init__(self, base_url: str) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        self._base_url = base_url

        if not self._base_url.endswith("/"):
            self._base_url += "/"

    async def _send_request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        headers: Optional[HeadersT] = None,
        json: Optional[RoutePoseDataT] = None,
    ) -> Optional[RoutesT]:
        async with self._session.request(
            method,
            self._base_url + path,
            headers=headers,  # type: ignore
            json=json,
        ) as response:
            response_str = await response.text()

        if response_str:
            return jsonlib.loads(response_str)

    async def get_routes(self) -> RoutesT:
        response = await self._send_request(
            "GET", "routes", headers={"Accept": "application/json"}
        )
        return cast(RoutesT, response)

    async def _remove_route(self, route: str):
        await self._send_request("DELETE", f"routes/{route}")

    async def _remove_all_routes(self):
        all_routes = await self.get_routes()
        tasks = list[Awaitable[None]]()
        for route in all_routes.keys():
            tasks.append(self._remove_route(route))

        await asyncio.gather(*tasks)

    async def _add_route(self, route: str, backend: str):
        await self._send_request(
            "POST",
            "routes",
            headers={"Content-Type": "application/json"},
            json=RoutePoseDataT(serverAddress=route, backend=backend),
        )

    async def _add_routes(self, routes: RoutesT):
        tasks = list[Awaitable[None]]()
        for route, backend in routes.items():
            tasks.append(self._add_route(route, backend))

        await asyncio.gather(*tasks)

    async def override_routes(self, routes: RoutesT):
        await self._remove_all_routes()
        if routes:
            await self._add_routes(routes)

    async def close(self):
        """Clean up the session"""
        await self._session.close()


class MCRouter:
    def __init__(
        self, mc_router_client: BaseMCRouterClient, domain: str, managed_sub_domain: str
    ) -> None:
        self._client = mc_router_client
        self._domain = domain
        self._managed_sub_domain = managed_sub_domain

    async def pull(self) -> MCRouterPullResultT:
        """
        pull routes from mc-router
        :raises Exception: if failed to get routes from mc-router, raised by aiohttp
        """
        routes = await self._client.get_routes()

        address_name_list = AddressNameListT()
        servers = ServersT()
        for server_address, backend in routes.items():
            if ":" in backend:
                _, server_port = backend.split(":")
                server_port = int(server_port)
            else:
                server_port = 25565

            server_and_address = server_address.split(
                f".{self._managed_sub_domain}.{self._domain}"
            )[0].split(".")
            server_name = server_and_address[0]
            if len(server_and_address) == 1:
                address_name = "*"
            else:
                address_name = server_and_address[1]

            if address_name not in address_name_list:
                address_name_list.append(address_name)
            if server_name not in servers:
                servers[server_name] = server_port

        return MCRouterPullResultT(address_name_list, servers)

    async def push(self, address_name_list: AddressNameListT, servers: ServersT):
        """
        push routes to mc-router
        :raises Exception: if failed to get routes from mc-router, raised by aiohttp
        """
        routes = RoutesT()
        for server_name, server_port in servers.items():
            for address_name in address_name_list:
                if address_name == "*":
                    sub_domain_base = f"{self._managed_sub_domain}"
                else:
                    sub_domain_base = f"{address_name}.{self._managed_sub_domain}"
                routes[f"{server_name}.{sub_domain_base}.{self._domain}"] = (
                    f"localhost:{server_port}"
                )

        logger.info(f"pushing routes to mc-router: {routes}")
        await self._client.override_routes(routes)
