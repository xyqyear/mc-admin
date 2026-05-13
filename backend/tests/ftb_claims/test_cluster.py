"""Pure flood-fill cluster correctness — no subprocess, no filesystem."""

from app.ftb_claims.cluster import build_clusters


def test_single_chunk_is_one_cluster():
    clusters = build_clusters(
        team_id="t1",
        region_dir_relpath="world/region",
        claims=[(0, 0)],
        force_loaded=[],
    )
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.chunks == [(0, 0)]
    assert cluster.force_loaded == []
    # Chunk (0,0) covers blocks 0..15; centroid is at the chunk center.
    assert cluster.centroid_block == (8.0, 8.0)
    assert cluster.bbox_chunk == (0, 0, 0, 0)
    assert cluster.regions == [(0, 0)]
    assert cluster.id == "t1#world/region#0"


def test_l_shape_is_one_cluster():
    # Five chunks in an L shape — all 4-connected.
    chunks = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=chunks,
        force_loaded=[],
    )
    assert len(clusters) == 1
    assert sorted(clusters[0].chunks) == sorted(chunks)
    assert clusters[0].bbox_chunk == (0, 0, 2, 2)


def test_disconnected_groups_yield_separate_clusters():
    chunks = [(0, 0), (1, 0), (10, 10), (10, 11)]
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=chunks,
        force_loaded=[],
    )
    assert len(clusters) == 2
    sizes = sorted(len(c.chunks) for c in clusters)
    assert sizes == [2, 2]
    # Cluster ids are unique within the same team/dim.
    assert clusters[0].id != clusters[1].id


def test_diagonal_chunks_are_not_connected():
    # 4-connectivity only — diagonals do not merge.
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=[(0, 0), (1, 1)],
        force_loaded=[],
    )
    assert len(clusters) == 2


def test_force_loaded_subset_is_preserved_in_cluster():
    chunks = [(0, 0), (1, 0), (2, 0)]
    force = [(1, 0)]
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=chunks,
        force_loaded=force,
    )
    assert len(clusters) == 1
    assert clusters[0].force_loaded == [(1, 0)]


def test_force_loaded_outside_claims_is_ignored():
    # A chunk in force_loaded but not in claims must not appear in the output.
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=[(0, 0)],
        force_loaded=[(0, 0), (99, 99)],
    )
    assert clusters[0].force_loaded == [(0, 0)]


def test_regions_are_deduplicated_and_cover_cluster_extent():
    # Two chunks in region (0,0) and two in region (1,0) (cx>=32).
    chunks = [(0, 0), (1, 0), (32, 0), (33, 0)]
    # Make them adjacent so it's a single cluster.
    chunks_connected = [(30, 0), (31, 0), (32, 0), (33, 0)]
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=chunks_connected,
        force_loaded=[],
    )
    assert len(clusters) == 1
    assert clusters[0].regions == [(0, 0), (1, 0)]


def test_centroid_is_average_block_position_of_claimed_chunks():
    # Two chunks at cx=0 and cx=10, cz=0 → centroid cx = 5 → block-x = 5*16+8 = 88.
    chunks = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)]
    clusters = build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=chunks,
        force_loaded=[],
    )
    assert len(clusters) == 1
    centroid_x, centroid_z = clusters[0].centroid_block
    assert centroid_x == 5 * 16 + 8
    assert centroid_z == 8.0


def test_no_chunks_yields_no_clusters():
    assert build_clusters(
        team_id="team",
        region_dir_relpath="world/region",
        claims=[],
        force_loaded=[],
    ) == []


def test_unresolved_dim_uses_underscore_in_cluster_id():
    clusters = build_clusters(
        team_id="t",
        region_dir_relpath=None,
        claims=[(0, 0)],
        force_loaded=[],
    )
    assert clusters[0].region_dir_relpath is None
    assert clusters[0].id == "t#_#0"


def test_cluster_order_is_stable():
    # Two equal-size clusters; should be ordered by (minZ, minX).
    chunks = [(10, 10), (10, 11), (-5, -5), (-5, -4)]
    clusters = build_clusters(
        team_id="t",
        region_dir_relpath="world/region",
        claims=chunks,
        force_loaded=[],
    )
    assert len(clusters) == 2
    # The cluster anchored at z=-5 sorts before the one at z=10.
    assert clusters[0].bbox_chunk[1] == -5
    assert clusters[1].bbox_chunk[1] == 10
