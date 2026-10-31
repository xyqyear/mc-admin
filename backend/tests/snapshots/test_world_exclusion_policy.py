import json

import pytest

from app.runtime_resources import current_runtime
from tests.support.regions import chunk_value, region_bytes

from .support import complete, scope

pytestmark = [pytest.mark.binary('restic'), pytest.mark.binary('fd'), pytest.mark.binary('mcmap')]


@pytest.mark.parametrize('kind', ['world', 'dimension', 'regions', 'chunks'])
async def test_world_recovery_removes_historically_excluded_data_and_rolls_back(world_case, kind):
    case = world_case
    mca = case.region / 'r.0.0.mca'
    case.config.snapshots.ignored_paths = ['world/region/r.0.0.mca']
    source = await case.snapshots.create_snapshot([case.region.parent])
    assert str(mca) in source.excludes
    assert mca not in await case.client.ls(source.id, case.region)
    case.config.snapshots.ignored_paths = ['world']
    mca.write_bytes(region_bytes(['live zero', 'live one']))
    before = mca.read_bytes()
    selected = scope(kind)
    assert (await case.commands.check_world_target(selected)).model_dump() == {'allowed': True, 'reason': None}
    candidates = await case.commands.eligible(selected)
    assert [row.id for row in candidates] == [source.id]
    assert candidates[0].skipped_paths == [] and candidates[0].skipped_count == 0

    accepted = await case.commands.restore(selected, source.id, 1)
    result = await complete(case, accepted)
    assert result['skipped_paths'] == []
    if kind == 'chunks':
        assert chunk_value(mca, 0) is None
        assert chunk_value(mca, 1) == 'live one'
    else:
        assert not mca.exists()
    safety = await case.snapshots.get_snapshot(result['safety_snapshot_id'])
    assert safety.excludes == []
    assert mca in await case.client.ls(safety.id, case.region)

    await case.commands.store.save_protection(accepted['restoration_id'], json.dumps({
        'version_format': 2, 'current': [str(case.region.parent)],
        'excluded': [str(case.region.parent)], 'mappings': [],
    }))
    rolled = await case.commands.rollback(accepted['restoration_id'], 1)
    await complete(case, rolled)
    assert mca.read_bytes() == before
    await complete(case, await case.commands.rollback(rolled['restoration_id'], 1))
    assert chunk_value(mca, 0) is None if kind == 'chunks' else not mca.exists()


async def test_world_preview_remains_usable_after_exclusion_configuration_changes(world_case):
    case = world_case
    case.config.snapshots.ignored_paths = ['world']
    source = await complete(case, await case.commands.create(scope('dimension'), 1))
    source_id = source['snapshot']['id']
    mca = case.region / 'r.0.0.mca'
    mca.write_bytes(region_bytes(['live zero', 'live one']))
    before = mca.read_bytes()
    cache = case.data / '.mcmap'
    cache.mkdir()
    (cache / 'palette.json').write_text('{}')
    previews = current_runtime().snapshot_previews
    assert previews is not None
    result = await complete(case, await previews.submit(scope('regions'), source_id, 1))
    assert result['kind'] == 'map' and result['skipped_paths'] == []
    assert mca.read_bytes() == before
    case.config.snapshots.ignored_paths = ['world/region', 'world/entities']
    accepted = await case.commands.restore(scope('regions'), source_id, 1, preview_id=result['preview_id'])
    await complete(case, accepted)
    assert chunk_value(mca, 0) == 'source zero'
    await complete(case, await case.commands.rollback(accepted['restoration_id'], 1))
    assert mca.read_bytes() == before
    await complete(case, await previews.end(result['preview_id'], 1))
