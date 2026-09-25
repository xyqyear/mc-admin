"""Translate execution claims into bounded, generation-bound journal scope."""

import posixpath
from collections.abc import Sequence
from pathlib import PurePosixPath

from ..servers.references import ServerRef
from .coordinator import ResourceClaim, ResourceKind
from .journal_types import ResourceReference


def journal_resources(
    servers: Sequence[ServerRef], claims: Sequence[ResourceClaim], *,
    default_kind: str = "server", empty_kind: str = "global",
) -> tuple[ResourceReference, ...]:
    generations = {server.server_id: server.generation for server in servers}
    kinds = {ResourceKind.FILES: "files", ResourceKind.MAP_CACHE: "cache", ResourceKind.ARCHIVE: "archive"}
    resources: set[ResourceReference] = set()
    for claim in claims:
        if claim.kind in {ResourceKind.PORT_ALLOCATION, ResourceKind.MAINTENANCE}:
            continue
        if claim.server_id and claim.server_id not in generations:
            raise ValueError("操作资源不属于已声明的服务器")
        path = str(PurePosixPath(claim.path))
        resources.add(ResourceReference(
            kinds[claim.kind], claim.server_id or None,
            generations.get(claim.server_id), "" if path == "." else path,
        ))
    covered = {resource.server_id for resource in resources}
    resources.update(ResourceReference(default_kind, server.server_id, server.generation) for server in servers if server.server_id not in covered)
    minimal = [resource for resource in resources if not any(
        other != resource and (other.kind, other.server_id) == (resource.kind, resource.server_id)
        and PurePosixPath(resource.path).is_relative_to(PurePosixPath(other.path))
        for other in resources
    )]
    if len(minimal) > 64:
        groups: dict[tuple[str, str | None, int | None], list[str]] = {}
        for resource in minimal:
            groups.setdefault((resource.kind, resource.server_id, resource.generation), []).append(resource.path or ".")
        minimal = []
        for (kind, server_id, generation), paths in groups.items():
            path = posixpath.commonpath(paths)
            minimal.append(ResourceReference(kind, server_id, generation, "" if path == "." else path))
    return tuple(sorted(minimal, key=lambda resource: (resource.kind, resource.server_id or "", resource.path))) or (ResourceReference(empty_kind),)


def require_contained_resources(parent: Sequence[ResourceReference], children: Sequence[ResourceReference]) -> None:
    for child in children:
        if not any(
            (resource.server_id, resource.generation) == (child.server_id, child.generation)
            and (resource.kind == child.kind or resource.kind in {"server", "world"})
            and PurePosixPath(child.path).is_relative_to(PurePosixPath(resource.path))
            for resource in parent
        ):
            raise RuntimeError("子操作不能扩大已声明的资源范围")
