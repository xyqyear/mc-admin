import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

import pytest

from app.servers.references import ServerRef
from app.snapshots.eligibility import select_sources
from app.snapshots.evidence import absence_tags, selection_tags
from app.snapshots.models import ResticSnapshot
from app.snapshots.path_mapping import SnapshotPathMapping
from app.snapshots.protection import SnapshotProtection
from app.snapshots.restoration_models import RestorationType
from app.snapshots.scopes import PathsScope, ResolvedScope, WorldScope
from app.snapshots.selection_models import RestorationSelection

from .reference_sources import select_sources as reference_sources


def world_selection(tmp_path, regions):
    data = tmp_path / 'survival/data'
    directories = [data / 'world' / name for name in ('region', 'entities', 'poi')]
    for directory in directories:
        directory.mkdir(parents=True)
    paths = tuple(sorted(directory / f'r.{x}.{z}.mca' for directory in directories for x, z in regions))
    for path in paths:
        path.write_bytes(b'unchanged terrain')
    scope = WorldScope(server_id='survival', selection=RestorationSelection(
        type=RestorationType.REGIONS, region_dir_relpath='world/region', regions=regions,
    ))
    ref = ServerRef('survival', 1, tmp_path, data.parent, data)
    resolved = ResolvedScope(scope, paths, (ref,), (), tuple(SnapshotPathMapping(path, path) for path in paths))
    return resolved, SnapshotProtection.capture(
        [data / '.mcmap'], data_paths=[data], mappings=resolved.mappings,
    )


def snapshot(number, paths, excludes=(), tags=()):
    return ResticSnapshot(
        id=f'{number:064x}', short_id=f'{number:08x}', time=datetime(2026, 10, 31, tzinfo=UTC),
        paths=[str(path) for path in paths], excludes=[str(path) for path in excludes],
        tags=list(tags), hostname='fixture', username='fixture', note=f'note {number}',
    )


def exhaustive_scope(resolved):
    paths = set(resolved.paths)
    for path in resolved.paths:
        _, rx, rz, _ = path.name.split('.')
        for x in range(int(rx) * 32, (int(rx) + 1) * 32):
            for z in range(int(rz) * 32, (int(rz) + 1) * 32):
                paths.add(path.parent / f'c.{x}.{z}.mcc')
    ordered = tuple(sorted(paths))
    return replace(resolved, paths=ordered, mappings=tuple(SnapshotPathMapping(path, path) for path in ordered))


async def test_region_candidates_preserve_exact_exclusions_absence_order_and_notes(tmp_path):
    resolved, protection = world_selection(tmp_path, [(-1, -1), (0, 0)])
    data = resolved.servers[0].data_path
    region, entities, poi = (data / 'world' / name for name in ('region', 'entities', 'poi'))
    mcc = region / 'c.-1.-1.mcc'
    mcc.write_bytes(b'external source chunk')
    sources = [
        snapshot(9, [data], [entities]),
        snapshot(2, [data], [mcc]),
        snapshot(8, [region]),
        snapshot(3, [data], tags=selection_tags([], [region / 'c.0.0.mcc'])),
        snapshot(6, [region], tags=absence_tags([entities, poi])),
        snapshot(1, [data], tags=selection_tags([], [])),
    ]
    actual = await select_sources(resolved, protection, resolved.paths, sources)
    full = exhaustive_scope(resolved)
    expected = await reference_sources(full, protection.with_mappings(full.mappings), resolved.paths, sources)
    assert actual == expected
    assert [row.id for row in actual] == [sources[i].id for i in (0, 1, 3, 4, 5)]
    assert actual[0].skipped_count == 2050
    assert len(actual[0].skipped_paths) == 100
    assert actual[1].skipped_paths == [str(mcc)]
    assert actual[2].skipped_paths == [str(region / 'c.0.0.mcc')]
    assert [row.note for row in actual] == ['note 9', 'note 2', 'note 3', 'note 6', 'note 1']
    assert mcc.read_bytes() == b'external source chunk'
    assert all(path.read_bytes() == b'unchanged terrain' for path in resolved.paths)
    assert list(data.rglob('*.mcc')) == [mcc]


@pytest.mark.parametrize('current', ['sidecar', 'parent', 'sibling'])
async def test_current_sidecar_rules_match_exhaustive_selection(tmp_path, current):
    resolved, protection = world_selection(tmp_path, [(-1, 0)])
    data = resolved.servers[0].data_path
    rules = {
        'sidecar': data / 'world/region/c.-1.0.mcc',
        'parent': data / 'world/region',
        'sibling': data / 'world/region/c.0.0.mcc',
    }
    protection = SnapshotProtection.capture([rules[current]], mappings=resolved.mappings)
    paths = protection.select_targets(resolved.paths)
    sources = [snapshot(1, [data], [data / 'world/poi/c.-2.0.mcc'])]
    actual = await select_sources(resolved, protection, paths, sources)
    full = exhaustive_scope(resolved)
    expected = await reference_sources(full, protection.with_mappings(full.mappings), paths, sources)
    assert actual == expected
    assert actual[0].skipped_count == (1 if current == 'sibling' else 2)


@pytest.mark.parametrize('policy', ['shared', 'distinct', 'protected'])
async def test_385_snapshots_six_regions_finish_without_starving_other_work(tmp_path, policy):
    resolved, protection = world_selection(tmp_path, [(x, 0) for x in range(-3, 3)])
    data = resolved.servers[0].data_path
    sources = [snapshot(
        i, [data],
        [data / 'world/entities'] if policy == 'protected' else
        [data / '.mcmap', data / '.mcmap' / str(i)] if policy == 'distinct' else [data / '.mcmap'],
        selection_tags([], []),
    ) for i in range(385)]
    delays = []
    started = perf_counter()
    query = asyncio.create_task(select_sources(resolved, protection, resolved.paths, sources))
    async def monitor():
        while not query.done():
            tick = perf_counter()
            await asyncio.sleep(0.01)
            delays.append(perf_counter() - tick)
    observer = asyncio.create_task(monitor())
    try:
        result = await asyncio.wait_for(query, 5)
        elapsed = perf_counter() - started
    finally:
        if not query.done():
            query.cancel()
        await asyncio.gather(query, observer, return_exceptions=True)
    assert [row.id for row in result] == [source.id for source in sources]
    assert [row.note for row in result] == [source.note for source in sources]
    assert all(row.skipped_count == (6150 if policy == 'protected' else 0) for row in result)
    assert delays and max(delays) < 0.5
    print(f'385 snapshots / 6 regions / {policy}: {elapsed:.4f}s, maximum scheduler gap {max(delays):.4f}s')


async def test_cancelled_catalog_query_settles_and_next_query_is_independent(tmp_path):
    resolved, protection = world_selection(tmp_path, [(0, 0)])
    source = snapshot(1, [resolved.servers[0].data_path])
    query = asyncio.create_task(select_sources(resolved, protection, resolved.paths, [source] * 10000))
    await asyncio.sleep(0)
    query.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(query, 1)
    result = await select_sources(resolved, protection, resolved.paths, [source])
    assert [row.id for row in result] == [source.id]


async def test_file_selection_of_mca_does_not_include_unselected_sidecars(tmp_path):
    resolved, protection = world_selection(tmp_path, [(0, 0)])
    data = resolved.servers[0].data_path
    path = data / 'world/region/r.0.0.mca'
    resolved = replace(
        resolved, scope=PathsScope(server_id='survival', paths=('world/region/r.0.0.mca',)),
        paths=(path,), mappings=(SnapshotPathMapping(path, path),),
    )
    protection = protection.with_mappings(resolved.mappings)
    sources = [snapshot(1, [data], [data / 'world/region/c.0.0.mcc'])]
    actual = await select_sources(resolved, protection, resolved.paths, sources)
    assert actual == await reference_sources(resolved, protection, resolved.paths, sources)
    assert [row.id for row in actual] == [sources[0].id]
    assert actual[0].skipped_count == 0
    assert actual[0].skipped_paths == []
