from typing import Iterable, List, Set, Tuple

from ..grid_geometry import connected_components
from .models import ClusterEntry


def build_clusters(
    *,
    team_id: str,
    region_dir_relpath: str | None,
    claims: Iterable[Tuple[int, int]],
    force_loaded: Iterable[Tuple[int, int]],
) -> List[ClusterEntry]:
    chunk_set: Set[Tuple[int, int]] = set(claims)
    if not chunk_set:
        return []
    force_set: Set[Tuple[int, int]] = set(force_loaded) & chunk_set
    components = connected_components(chunk_set)
    rel = region_dir_relpath if region_dir_relpath is not None else "_"
    entries: List[ClusterEntry] = []
    for idx, comp in enumerate(components):
        min_cx = min(cx for cx, _ in comp)
        max_cx = max(cx for cx, _ in comp)
        min_cz = min(cz for _, cz in comp)
        max_cz = max(cz for _, cz in comp)
        sum_x = sum(cx for cx, _ in comp)
        sum_z = sum(cz for _, cz in comp)
        n = len(comp)
        # Block-space centroid; +8 shifts from chunk NW corner to chunk center.
        centroid_x = (sum_x / n) * 16 + 8
        centroid_z = (sum_z / n) * 16 + 8
        regions = sorted({(cx >> 5, cz >> 5) for cx, cz in comp})
        force_in_cluster = sorted([c for c in comp if c in force_set])
        entries.append(
            ClusterEntry(
                id=f"{team_id}#{rel}#{idx}",
                region_dir_relpath=region_dir_relpath,
                chunks=comp,
                force_loaded=force_in_cluster,
                centroid_block=(centroid_x, centroid_z),
                bbox_chunk=(min_cx, min_cz, max_cx, max_cz),
                regions=regions,
            )
        )
    return entries
