"""
Simplified MC Router Client

Direct client implementation for mc-router without wrapper abstractions.
"""

import asyncio
import json as jsonlib
from typing import (
    Awaitable,
    Literal,
    Optional,
    TypedDict,
    cast,
)

import aiohttp

from ..logger import logger


class RoutePoseDataT(TypedDict):
    serverAddress: str
    backend: str


RoutesT = dict[str, str]


class MCRouterClient:
    """
    Direct MC Router client without wrapper abstractions.

    This client provides simple methods to get and override routes
    in the mc-router service.
    """

    def __init__(self, base_url: str) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        self._base_url = base_url

        if not self._base_url.endswith("/"):
            self._base_url += "/"

    async def _send_request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[RoutePoseDataT] = None,
    ) -> Optional[RoutesT]:
        async with self._session.request(
            method,
            self._base_url + path,
            headers=headers,
            json=json,
        ) as response:
            response_str = await response.text()

        if response_str:
            return jsonlib.loads(response_str)

    async def get_routes(self) -> RoutesT:
        """Get all current routes from mc-router"""
        response = await self._send_request(
            "GET", "routes", headers={"Accept": "application/json"}
        )
        return cast(RoutesT, response)

    async def _remove_route(self, route: str):
        """Remove a single route"""
        await self._send_request("DELETE", f"routes/{route}")

    async def _remove_all_routes(self):
        """Remove all current routes"""
        all_routes = await self.get_routes()
        tasks = list[Awaitable[None]]()
        for route in all_routes.keys():
            tasks.append(self._remove_route(route))

        await asyncio.gather(*tasks)

    async def _add_route(self, route: str, backend: str):
        """Add a single route"""
        await self._send_request(
            "POST",
            "routes",
            headers={"Content-Type": "application/json"},
            json=RoutePoseDataT(serverAddress=route, backend=backend),
        )

    async def _add_routes(self, routes: RoutesT):
        """Add multiple routes in parallel"""
        tasks = list[Awaitable[None]]()
        for route, backend in routes.items():
            tasks.append(self._add_route(route, backend))

        await asyncio.gather(*tasks)

    async def override_routes(self, routes: RoutesT):
        """
        Replace all routes with the provided route dictionary.

        This method:
        1. Removes all existing routes
        2. Adds all provided routes

        Args:
            routes: Dictionary mapping server addresses to backends
        """
        logger.info(f"Overriding MC Router with {len(routes)} routes")
        await self._remove_all_routes()
        if routes:
            await self._add_routes(routes)

    async def get_routes_diff(self, target_routes: RoutesT) -> dict:
        """
        Calculate the difference between current routes and target routes.

        Returns a dictionary with:
        - routes_to_add: Routes that need to be added
        - routes_to_remove: Routes that need to be removed
        - routes_to_update: Routes that need to be updated with current/target values

        Args:
            target_routes: Dictionary mapping server addresses to backends

        Returns:
            Dictionary with diff categorization
        """
        current_routes = await self.get_routes()

        routes_to_add = {}
        routes_to_remove = {}
        routes_to_update = {}

        # Check for routes to add or update
        for addr, backend in target_routes.items():
            if addr not in current_routes:
                routes_to_add[addr] = backend
            elif current_routes[addr] != backend:
                routes_to_update[addr] = {
                    "current": current_routes[addr],
                    "target": backend
                }

        # Check for routes to remove
        for addr in current_routes:
            if addr not in target_routes:
                routes_to_remove[addr] = current_routes[addr]

        return {
            "routes_to_add": routes_to_add,
            "routes_to_remove": routes_to_remove,
            "routes_to_update": routes_to_update
        }

    async def close(self):
        """Clean up the session"""
        await self._session.close()
