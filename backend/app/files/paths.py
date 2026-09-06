from pathlib import Path

from fastapi import HTTPException

from ..utils import async_fs


async def resolve_file_path(base_path: Path, path: str) -> Path:
    candidate = base_path / path.lstrip("/")
    try:
        await async_fs.resolve_inside(base_path, candidate)
    except async_fs.PathOutsideBaseError:
        raise HTTPException(status_code=400, detail="Path escapes file directory")
    # Rename and unlink must act on a symlink itself, not its resolved target.
    return candidate


def validate_file_name(name: str) -> None:
    if not name or name in {".", ".."} or "/" in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
