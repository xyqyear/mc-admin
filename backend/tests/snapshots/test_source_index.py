from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

import pytest

from app.snapshots.coverage import PathIndex
from app.snapshots.evidence import selection_tags
from app.snapshots.models import ResticSnapshot
from app.snapshots.path_mapping import SnapshotPathMapping
from app.snapshots.protection import SnapshotProtection
from app.snapshots.source import SnapshotSource

from .reference_sources import protect


def test_path_index_distinguishes_ancestors_descendants_and_siblings():
    paths = [Path('/data/world'), Path('/data/world/region/a'), Path('/data/world2'), Path('/other')]
    index = PathIndex(paths)
    assert index.contains(Path('/data/world/region/r.0.0.mca'))
    assert not index.contains(Path('/data/worldwide'))
    assert not index.contains(Path('/data'))
    assert list(index.ancestors(Path('/data/world/region/a'))) == paths[1::-1]
    assert list(index.descendants(Path('/data/world'))) == paths[:2]
    assert index.overlaps(Path('/data'))
    assert not index.overlaps(Path('/unrelated'))
    relative = PathIndex([Path('.')])
    assert relative.contains(Path('world/region'))
    assert not relative.contains(Path('/world/region'))
    assert list(index.descendants(Path('.'))) == []


async def test_source_projection_matches_exhaustive_rules_with_nested_exclusions(tmp_path):
    roots = [tmp_path / name for name in ('world', 'world2', 'plugins')]
    for path in roots:
        path.mkdir()
    targets = [roots[0] / 'region/a', roots[1], roots[2]]
    choices = [tmp_path, roots[0], roots[0] / 'region/a', roots[0] / 'region/a/child', roots[1] / 'keep', tmp_path / 'elsewhere']
    protection = SnapshotProtection.capture(
        [roots[2] / 'private'],
        mappings=[SnapshotPathMapping(path, path) for path in targets],
    )
    for excluded in combinations(choices, 2):
        for tags in ([], selection_tags([], [roots[1] / 'historical'])):
            snapshot = ResticSnapshot(
                id='a' * 64, short_id='a' * 8, time=datetime.now(UTC),
                hostname='fixture', username='fixture', paths=[str(tmp_path)],
                excludes=[str(path) for path in excluded], tags=tags,
            )
            actual = await SnapshotSource(snapshot).protect(protection)
            expected = await protect(protection, snapshot)
            assert actual == expected


@pytest.mark.parametrize('excluded', [[], ['/data/world/cache'], ['/data/world']])
def test_compiled_coverage_preserves_parent_restore_and_protected_roots(excluded):
    source = SnapshotSource(ResticSnapshot(
        id='a' * 64, short_id='a' * 8, time=datetime.now(UTC), hostname='fixture',
        username='fixture', paths=['/data/world'], excludes=excluded,
    ))
    protection = SnapshotProtection.capture(())
    assert source.covers(Path('/data/world'), protection) is ('/data/world' not in excluded)
    assert not source.covers(Path('/data/world2'), protection)
    assert source.covers(Path('/data/world/cache/x'), protection) is (not excluded)
