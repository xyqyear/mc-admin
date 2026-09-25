"""Pure desired connectivity, differences and observation state."""

from dataclasses import dataclass
from typing import Literal, NamedTuple

from .types import AddRecordT
from .utils import RecordDiff


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


@dataclass(frozen=True)
class RouteDiff:
    routes_to_add: dict[str, str]
    routes_to_remove: dict[str, str]
    routes_to_update: dict[str, dict[str, str]]

    @property
    def pending(self) -> bool:
        return bool(self.routes_to_add or self.routes_to_remove or self.routes_to_update)

    def as_dict(self) -> dict:
        return {
            "routes_to_add": self.routes_to_add,
            "routes_to_remove": self.routes_to_remove,
            "routes_to_update": self.routes_to_update,
        }


def diff_routes(current: dict[str, str], target: dict[str, str], *, allow_removals: bool = True) -> RouteDiff:
    return RouteDiff(
        {key: value for key, value in target.items() if key not in current},
        {key: value for key, value in current.items() if key not in target} if allow_removals else {},
        {key: {"current": current[key], "target": value} for key, value in target.items() if key in current and current[key] != value},
    )


@dataclass(frozen=True)
class DesiredConnectivity:
    records: tuple[AddRecordT, ...]
    routes: tuple[RouteEntry, ...]
    unknown_servers: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.records or not self.routes

    @property
    def allow_removals(self) -> bool:
        return not self.unknown_servers and not self.empty


@dataclass(frozen=True)
class ConnectivityObservation:
    dns_diff: RecordDiff | None
    router_diff: RouteDiff | None
    unknown_servers: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    empty_desired: bool = False

    @property
    def dns_known(self) -> bool:
        return self.dns_diff is not None

    @property
    def router_known(self) -> bool:
        return self.router_diff is not None

    @property
    def state(self) -> Literal["ready", "pending", "degraded", "empty"]:
        if self.issues or not self.dns_known or not self.router_known:
            return "degraded"
        if self.empty_desired:
            return "empty"
        dns = self.dns_diff
        if (dns and any(dns)) or (self.router_diff and self.router_diff.pending):
            return "pending"
        return "ready"


def generate_dns_records(addresses: dict[str, AddressInfo], servers: list[str], managed: str, ttl: int, domain: str) -> list[DNSRecord]:
    records = []
    for name, address in addresses.items():
        base = managed if name == "*" else f"{name}.{managed}"
        records.append(DNSRecord(f"*.{base}", address.type, address.host, ttl))
        records.extend(DNSRecord(f"_minecraft._tcp.{server}.{base}", "SRV", f"0 5 {address.port} {server}.{base}.{domain}", ttl) for server in servers)
    return records


def generate_routes(addresses: dict[str, AddressInfo], servers: dict[str, int], managed: str, domain: str) -> list[RouteEntry]:
    return [
        RouteEntry(f"{server}.{managed if name == '*' else f'{name}.{managed}'}.{domain}", f"localhost:{port}")
        for server, port in servers.items() for name in addresses
    ]
