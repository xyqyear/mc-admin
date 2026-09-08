"""
Simplified MC Router Client

Direct client implementation for mc-router without wrapper abstractions.
"""

import json as jsonlib
from collections.abc import Awaitable
from typing import (
    Any,
    Literal,
    TypedDict,
)

import httpx2

from ..logger import logger
from .utils import wait_for_updates


class RoutePoseDataT(TypedDict):
    serverAddress: str
    backend: str


RoutesT = dict[str, str]


class MCRouterProtocolError(ValueError):
    """The router returned an invalid route response."""


class MCRouterClient:
    """
    Direct MC Router client without wrapper abstractions.

    This client provides simple methods to get and override routes
    in the mc-router service.
    """

    def __init__(self, base_url: str) -> None:
        self._client = httpx2.AsyncClient(timeout=10.0)

        self._base_url = base_url

        if not self._base_url.endswith("/"):
            self._base_url += "/"

    async def _send_request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        headers: dict[str, str] | None = None,
        json: RoutePoseDataT | None = None,
    ) -> dict[str, Any] | None:
        response = await self._client.request(
            method,
            self._base_url + path,
            headers=headers,
            json=json,
        )
        if method == "DELETE" and response.status_code == 404:
            return None
        response.raise_for_status()
        response_str = response.text

        if response_str:
            return jsonlib.loads(response_str)

    async def get_routes(self) -> RoutesT:
        """Get all current routes from mc-router"""
        response = await self._send_request(
            "GET", "routes", headers={"Accept": "application/json"}
        )
        if not isinstance(response, dict):
            raise MCRouterProtocolError("MC Router 路由响应必须是对象")
        routes: RoutesT = {}
        for address, route in response.items():
            backend = route.get("backend") if isinstance(route, dict) else route
            if not isinstance(backend, str) or not backend:
                raise MCRouterProtocolError(f"MC Router 路由 {address} 缺少有效的后端地址")
            routes[address] = backend
        return routes

    async def _remove_route(self, route: str):
        """Remove a single route"""
        await self._send_request("DELETE", f"routes/{route}")

    async def _remove_all_routes(self):
        """Remove all current routes"""
        all_routes = await self.get_routes()
        tasks = list[Awaitable[None]]()
        for route in all_routes:
            tasks.append(self._remove_route(route))

        await wait_for_updates(*tasks)

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

        await wait_for_updates(*tasks)

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
                    "target": backend,
                }

        # Check for routes to remove
        for addr in current_routes:
            if addr not in target_routes:
                routes_to_remove[addr] = current_routes[addr]

        return {
            "routes_to_add": routes_to_add,
            "routes_to_remove": routes_to_remove,
            "routes_to_update": routes_to_update,
        }

    async def close(self):
        """Clean up the client"""
        await self._client.aclose()
