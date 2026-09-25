from collections.abc import AsyncGenerator

from ..background_tasks import TaskProgress, get_task_manager
from ..logger import get_logger
from ..mcmap import runner as mcmap_runner
from ..mcmap.events import (
    MCMAP_PRUNE_EVENT_ADAPTER,
    MCMapChunksPrunedEvent,
    MCMapErrorEvent,
    MCMapPruneProgressEvent,
    MCMapPruneRegionDirEvent,
    MCMapPruneResultEvent,
    MCMapRegionPrunedEvent,
)
from .geometry import PruneEventPathMapper, build_preview_geometry
from .models import ChunkPruneTaskMetadata


class ChunkPruneError(Exception):
    pass


async def run_prune(
    metadata: ChunkPruneTaskMetadata, *, dry_run: bool
) -> AsyncGenerator[TaskProgress]:
    logger = get_logger()
    selected_cells_by_dimension: dict[str, set[tuple[int, int]]] = {}
    path_mapper = PruneEventPathMapper(metadata.data_path)
    progress_percent = 0.0
    saw_result = False

    async with mcmap_runner.prune_inhabited(
        path=metadata.data_path,
        threshold_ticks=metadata.threshold_ticks,
        mode=metadata.mode,
        dry_run=dry_run,
        owned_by=metadata.data_path,
        exclude_ftb_claims=metadata.claims_file,
    ) as proc:
        async for event in proc.events(MCMAP_PRUNE_EVENT_ADAPTER):
            task = get_task_manager().get_task(metadata.task_id)
            if task is not None and task.cancel_requested:
                await proc.terminate()
                yield TaskProgress(progress=progress_percent, message="已取消")
                return

            if isinstance(event, MCMapPruneRegionDirEvent):
                yield TaskProgress(
                    progress=progress_percent,
                    message=f"发现 {event.regions} 个区域文件",
                )
            elif isinstance(event, MCMapPruneProgressEvent):
                if event.regions_total > 0:
                    progress_percent = (
                        event.regions_processed / event.regions_total * 100
                    )
                yield TaskProgress(
                    progress=progress_percent,
                    message=(
                        f"已处理 {event.regions_processed}/"
                        f"{event.regions_total} 个区域文件"
                    ),
                )
            elif isinstance(event, MCMapChunksPrunedEvent):
                relpath = path_mapper.region_relpath(event.region)
                if relpath is None:
                    logger.warning(
                        "chunk-prune: ignored chunks event outside region dir: %s",
                        event.region,
                    )
                    continue
                _add_affected_region(
                    metadata, relpath, event.region_x, event.region_z
                )
                if dry_run:
                    selected_cells_by_dimension.setdefault(relpath, set()).update(
                        (chunk.chunk_x, chunk.chunk_z) for chunk in event.chunks
                    )
            elif isinstance(event, MCMapRegionPrunedEvent):
                relpath = path_mapper.region_relpath(event.region)
                if relpath is None:
                    logger.warning(
                        "chunk-prune: ignored region event outside region dir: %s",
                        event.region,
                    )
                    continue
                _add_affected_region(
                    metadata, relpath, event.region_x, event.region_z
                )
                if dry_run:
                    selected_cells_by_dimension.setdefault(relpath, set()).add(
                        (event.region_x, event.region_z)
                    )
            elif isinstance(event, MCMapPruneResultEvent):
                saw_result = True
                result = event.model_dump(exclude_none=True)
                result["threshold_seconds"] = metadata.threshold_seconds
                result["threshold_ticks"] = metadata.threshold_ticks
                result["affected_region_counts_by_dimension"] = {
                    relpath: len(regions)
                    for relpath, regions in sorted(
                        metadata.affected_regions_by_dimension.items()
                    )
                }
                if dry_run:
                    metadata.geometry = build_preview_geometry(
                        metadata,
                        selected_cells_by_dimension,
                    )
                metadata.result = result
                yield TaskProgress(
                    progress=100,
                    message="清理预览完成" if dry_run else "区块清理完成",
                    result=result,
                )
            elif isinstance(event, MCMapErrorEvent):
                raise ChunkPruneError(event.message)

        if proc.returncode not in (0, None):
            stderr = (await proc.stderr()).strip()
            raise ChunkPruneError(stderr or "mcmap prune-inhabited failed")
    if not saw_result:
        raise ChunkPruneError("mcmap prune-inhabited produced no result")

def _add_affected_region(
    metadata: ChunkPruneTaskMetadata,
    region_dir_relpath: str,
    rx: int,
    rz: int,
) -> None:
    metadata.affected_regions_by_dimension.setdefault(
        region_dir_relpath, set()
    ).add((rx, rz))
