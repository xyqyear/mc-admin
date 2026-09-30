import base64
import binascii
import json
from collections.abc import Sequence
from pathlib import Path

from ..errors import PublicOperationError
from .models import ResticSnapshot

_ABSENCE_TAG = "mc-admin-absence-v1:"


def absence_tags(paths: Sequence[Path]) -> list[str]:
    if not paths:
        return []
    value = json.dumps([str(path) for path in paths], separators=(",", ":")).encode()
    tag = _ABSENCE_TAG + base64.urlsafe_b64encode(value).decode()
    if len(tag) > 32768:
        raise PublicOperationError("快照缺失目录记录过大，请缩小选择范围")
    return [tag]


def snapshot_absence(snapshot: ResticSnapshot) -> tuple[Path, ...]:
    tags = [tag for tag in snapshot.tags if tag.startswith(_ABSENCE_TAG)]
    if not tags:
        return ()
    try:
        if len(tags) != 1 or len(tags[0]) > 32768:
            raise ValueError("Invalid absence metadata size")
        values = json.loads(
            base64.b64decode(
                tags[0][len(_ABSENCE_TAG) :], altchars=b"-_", validate=True
            )
        )
        if not isinstance(values, list) or not all(
            isinstance(value, str)
            and Path(value).is_absolute()
            and ".." not in Path(value).parts
            for value in values
        ):
            raise ValueError("Invalid absence paths")
        return tuple(Path(value) for value in values)
    except (ValueError, binascii.Error) as error:
        raise PublicOperationError("快照缺失目录记录无效，未执行恢复") from error
