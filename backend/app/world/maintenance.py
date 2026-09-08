"""Resolve snapshot targets to the servers whose data they cover."""

from collections.abc import Sequence
from pathlib import Path

from ..minecraft import DockerMCManager
from ..minecraft.properties import read_level_name
from ..utils import async_fs
from .layout import discover_world_root_paths


def paths_overlap(first: Path, second: Path) -> bool:
    return first.is_relative_to(second) or second.is_relative_to(first)


async def affected_servers(
    manager: DockerMCManager, targets: Sequence[Path], *, world_only: bool = False
) -> list[str]:
    resolved = [await async_fs.resolve(path) for path in targets]
    affected: list[str] = []
    for instance in await manager.get_all_instances():
        project = await async_fs.resolve(instance.get_project_path())
        if not any(paths_overlap(path, project) for path in resolved):
            continue
        if world_only:
            data = await async_fs.resolve(instance.get_data_path())
            if any(data.is_relative_to(path) for path in resolved):
                affected.append(instance.get_name())
                continue
            roots = await discover_world_root_paths(data)
            world_paths = [await async_fs.resolve(root.path) for root in roots]
            try:
                world_paths.append(
                    await async_fs.resolve_inside(
                        data, data / await read_level_name(data)
                    )
                )
            except async_fs.PathOutsideBaseError:
                pass
            if not any(
                data.is_relative_to(path)
                or any(paths_overlap(path, world) for world in world_paths)
                for path in resolved
            ):
                continue
        affected.append(instance.get_name())
    return affected
