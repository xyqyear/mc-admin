from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

Cell = tuple[int, int]
Vertex = tuple[int, int]
Ring = list[Vertex]


@dataclass(frozen=True)
class GridShapeData:
    id: str
    cell_count: int
    bbox: tuple[int, int, int, int]
    rings: list[Ring]


def connected_components(cells: Iterable[Cell]) -> list[list[Cell]]:
    remaining = set(cells)
    components: list[list[Cell]] = []
    while remaining:
        seed = next(iter(remaining))
        component: list[Cell] = []
        queue: deque[Cell] = deque([seed])
        remaining.discard(seed)
        while queue:
            x, z = queue.popleft()
            component.append((x, z))
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (x + dx, z + dz)
                if neighbor in remaining:
                    remaining.discard(neighbor)
                    queue.append(neighbor)
        component.sort()
        components.append(component)
    components.sort(key=lambda comp: (min(z for _, z in comp), min(x for x, _ in comp)))
    return components


def compute_boundary_rings(cells: Iterable[Cell]) -> list[Ring]:
    cell_set = set(cells)
    if not cell_set:
        return []

    def has(x: int, z: int) -> bool:
        return (x, z) in cell_set

    adj: dict[Vertex, list[Vertex]] = {}

    def push_edge(start: Vertex, end: Vertex) -> None:
        adj.setdefault(start, []).append(end)

    for x, z in sorted(cell_set):
        if not has(x, z - 1):
            push_edge((x + 1, z), (x, z))
        if not has(x, z + 1):
            push_edge((x, z + 1), (x + 1, z + 1))
        if not has(x - 1, z):
            push_edge((x, z), (x, z + 1))
        if not has(x + 1, z):
            push_edge((x + 1, z + 1), (x + 1, z))

    rings: list[Ring] = []
    while adj:
        start = next(iter(adj))
        ring: Ring = [start]
        cursor = _pop_adj(adj, start)
        if cursor is None:
            adj.pop(start, None)
            continue
        while cursor != start:
            ring.append(cursor)
            next_cursor = _pop_adj(adj, cursor)
            if next_cursor is None:
                break
            cursor = next_cursor
        if len(ring) >= 3:
            rings.append(_simplify_collinear(ring))
    return rings


def build_grid_shapes(cells: Iterable[Cell], *, id_prefix: str) -> list[GridShapeData]:
    shapes: list[GridShapeData] = []
    for idx, component in enumerate(connected_components(cells)):
        xs = [x for x, _ in component]
        zs = [z for _, z in component]
        rings = compute_boundary_rings(component)
        rings.sort(key=_ring_area_abs, reverse=True)
        shapes.append(
            GridShapeData(
                id=f"{id_prefix}-{idx}",
                cell_count=len(component),
                bbox=(min(xs), min(zs), max(xs), max(zs)),
                rings=rings,
            )
        )
    return shapes


def _pop_adj(adj: dict[Vertex, list[Vertex]], key: Vertex) -> Vertex | None:
    values = adj.get(key)
    if not values:
        return None
    value = values.pop(0)
    if not values:
        adj.pop(key, None)
    return value


def _simplify_collinear(ring: Ring) -> Ring:
    if len(ring) < 3:
        return ring
    out: Ring = []
    n = len(ring)
    for i, current in enumerate(ring):
        prev = ring[(i - 1 + n) % n]
        nxt = ring[(i + 1) % n]
        dx1 = current[0] - prev[0]
        dz1 = current[1] - prev[1]
        dx2 = nxt[0] - current[0]
        dz2 = nxt[1] - current[1]
        if dx1 * dz2 - dz1 * dx2 == 0 and dx1 * dx2 + dz1 * dz2 > 0:
            continue
        out.append(current)
    return out


def _ring_area_abs(ring: Ring) -> int:
    area2 = 0
    for idx, (x1, z1) in enumerate(ring):
        x2, z2 = ring[(idx + 1) % len(ring)]
        area2 += x1 * z2 - x2 * z1
    return abs(area2)
