import json
from collections.abc import Sequence

from app.servers.references import ServerRef
from app.snapshots.restoration_models import (
    Restoration,
    RestorationStatus,
    RestorationType,
)


def legacy_world_restoration(
    identity: str,
    reference: ServerRef,
    source_id: str,
    safety_id: str,
    absent_dirs: Sequence[str] = (),
) -> Restoration:
    return Restoration(
        id=identity,
        server_id=reference.server_id,
        server_generation=reference.generation,
        type=RestorationType.WORLD,
        source_snapshot_id=source_id,
        safety_snapshot_id=safety_id,
        status=RestorationStatus.SUCCEEDED,
        entry_point="world",
        is_rollback=False,
        selection_json=json.dumps(
            {"type": "world", "absent_directories": list(absent_dirs)}
        ),
        scope_json=json.dumps(
            {
                "version": 1,
                "scope": {
                    "kind": "world",
                    "server_id": reference.server_id,
                    "selection": {"type": "world"},
                },
            }
        ),
        targets_json=json.dumps(
            [{"server_id": reference.server_id, "generation": reference.generation}]
        ),
    )
