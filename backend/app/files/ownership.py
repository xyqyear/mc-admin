"""Ownership repair tasks for server files."""

from collections.abc import AsyncGenerator
from pathlib import Path

from ..background_tasks.types import TaskProgress
from ..utils.exec import exec_command
from .utils import get_uid_gid


async def restore_tree_ownership_task(
    base_path: Path,
) -> AsyncGenerator[TaskProgress, None]:
    try:
        uid, gid = await get_uid_gid(base_path)
    except FileNotFoundError:
        raise RuntimeError("服务器数据目录不存在")

    owner = f"{uid}:{gid}"
    yield TaskProgress(progress=None, message=f"正在修复文件所有权为 {owner}...")

    try:
        await exec_command("chown", "-R", owner, str(base_path))
    except FileNotFoundError:
        raise RuntimeError("chown命令不可用")
    except PermissionError:
        raise RuntimeError("无权限修复文件所有权")
    except RuntimeError as e:
        raise RuntimeError(f"修复文件所有权失败: {e}")

    yield TaskProgress(
        progress=100,
        message="文件所有权修复完成",
        result={"uid": uid, "gid": gid},
    )
