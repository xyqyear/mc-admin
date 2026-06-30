from app.grid_geometry import build_grid_shapes, compute_boundary_rings, connected_components


def normalize_ring(ring):
    rotations = [ring[i:] + ring[:i] for i in range(len(ring))]
    return min(rotations)


def normalize_rings(rings):
    return sorted(normalize_ring(ring) for ring in rings)


def test_connected_components_uses_four_connectivity():
    components = connected_components([(0, 0), (1, 0), (2, 2), (3, 3)])

    assert components == [[(0, 0), (1, 0)], [(2, 2)], [(3, 3)]]


def test_boundary_ring_simplifies_rectangle():
    rings = compute_boundary_rings([(0, 0), (1, 0), (0, 1), (1, 1)])

    assert normalize_rings(rings) == normalize_rings(
        [[(2, 0), (0, 0), (0, 2), (2, 2)]]
    )


def test_boundary_ring_keeps_hole():
    cells = [
        (x, z)
        for x in range(3)
        for z in range(3)
        if (x, z) != (1, 1)
    ]

    rings = compute_boundary_rings(cells)

    assert normalize_rings(rings) == normalize_rings(
        [
            [(3, 0), (0, 0), (0, 3), (3, 3)],
            [(1, 1), (2, 1), (2, 2), (1, 2)],
        ]
    )


def test_build_grid_shapes_returns_component_metadata():
    shapes = build_grid_shapes(
        [(0, 0), (1, 0), (10, 10)],
        id_prefix="world-region",
    )

    assert len(shapes) == 2
    assert shapes[0].id == "world-region-0"
    assert shapes[0].cell_count == 2
    assert shapes[0].bbox == (0, 0, 1, 0)
    assert shapes[1].id == "world-region-1"
    assert shapes[1].cell_count == 1
    assert shapes[1].bbox == (10, 10, 10, 10)
