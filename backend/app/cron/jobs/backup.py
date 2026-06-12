import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, List, Optional, cast

import aiofiles.os as aioos
import httpx2
from pydantic import ConfigDict, Field, field_validator, model_validator

from ...config import settings
from ...dynamic_config.schemas import BaseConfigSchema
from ...minecraft import docker_mc_manager
from ...snapshots import snapshot_service
from ...utils import async_fs
from ...world import (
    GLOBAL_LOCK_KEY,
    LockHolder,
    ServerOperationKind,
    server_operation_lock,
)
from ..types import ExecutionContext


class BackupJobParams(BaseConfigSchema):
    """备份定时任务参数。"""

    model_config = ConfigDict(title="备份任务参数")

    # Backup target configuration
    server_id: Annotated[
        Optional[str],
        Field(
            title="服务器 ID",
            description="可选要备份的服务器；留空表示备份所有服务器。",
        ),
    ] = None
    path: Annotated[
        Optional[str],
        Field(title="备份路径", description="服务器数据目录内的可选路径。"),
    ] = None

    # Forget configuration
    enable_forget: Annotated[
        bool,
        Field(title="运行 forget", description="是否在备份后运行 restic forget。"),
    ] = True

    # Forget retention policies (all optional, but at least one must be specified if enable_forget=True)
    keep_last: Annotated[
        Optional[int], Field(title="保留最近快照数", description="保留最近的 n 个快照。")
    ] = None
    keep_hourly: Annotated[
        Optional[int],
        Field(title="每小时保留", description="在最近 n 小时内每小时保留一次。"),
    ] = None
    keep_daily: Annotated[
        Optional[int],
        Field(title="每天保留", description="在最近 n 天内每天保留一次。"),
    ] = None
    keep_weekly: Annotated[
        Optional[int],
        Field(title="每周保留", description="在最近 n 周内每周保留一次。"),
    ] = None
    keep_monthly: Annotated[
        Optional[int],
        Field(title="每月保留", description="在最近 n 月内每月保留一次。"),
    ] = None
    keep_yearly: Annotated[
        Optional[int],
        Field(title="每年保留", description="在最近 n 年内每年保留一次。"),
    ] = None
    keep_tag: Annotated[
        Optional[List[str]],
        Field(title="保留标签", description="保留带有这些标签的所有快照。"),
    ] = None
    keep_within: Annotated[
        Optional[str],
        Field(
            title="按时间范围保留",
            description='在指定时长内保留所有快照，例如 "4d" 或 "2y5m7d3h"。',
        ),
    ] = None

    # Forget options
    prune: Annotated[
        bool,
        Field(title="运行 prune", description="是否在 forget 后运行 restic prune。"),
    ] = True

    # Uptime Kuma integration
    uptimekuma_url: Annotated[
        Optional[str],
        Field(title="Uptime Kuma 推送 URL", description="Uptime Kuma 推送监控 URL，可选。"),
    ] = None

    @model_validator(mode="after")
    def validate_forget_params(self):
        """Validate that if forget is enabled, at least one retention policy is specified"""
        if not self.enable_forget:
            return self

        retention_params = [
            self.keep_last,
            self.keep_hourly,
            self.keep_daily,
            self.keep_weekly,
            self.keep_monthly,
            self.keep_yearly,
            self.keep_tag,
            self.keep_within,
        ]
        if all(
            param is None
            or (isinstance(param, list) and len(param) == 0)
            or (isinstance(param, str) and param.strip() == "")
            for param in retention_params
        ):
            raise ValueError("启用forget时至少需要指定一个保留策略参数")

        return self

    @field_validator("path")
    @classmethod
    def validate_path_requires_server_id(cls, v, info):
        """Validate that path cannot be specified without server_id"""
        if v is not None and info.data.get("server_id") is None:
            raise ValueError("不能在未指定server_id的情况下指定路径")
        return v


def _get_snapshot_service():
    """Get configured snapshot service instance"""
    if not snapshot_service:
        raise RuntimeError("Restic未配置。请在config.toml中添加restic设置")
    return snapshot_service


async def _send_uptimekuma_notification(
    context: ExecutionContext, uptimekuma_url: str, ok: bool, msg: str, ping: float
):
    """
    Send notification to Uptime Kuma push monitor

    Args:
        context: Execution context for logging
        uptimekuma_url: Uptime Kuma push monitor URL
        ok: Whether the backup was successful
        msg: Message (OK for success, error message for failure)
        ping: Running time in seconds
    """
    context.log(f"发送 Uptime Kuma 通知到: {uptimekuma_url}")

    params = {
        "status": "up" if ok else "down",
        "msg": msg,
        "ping": int(ping * 1000),
    }

    try:
        async with httpx2.AsyncClient(timeout=10) as client:
            response = await client.get(uptimekuma_url, params=params)
    except httpx2.HTTPError as e:
        context.log(f"发送 Uptime Kuma 通知失败: {str(e)}")
        return
    except Exception as e:
        context.log(f"Uptime Kuma 通知时发生未知错误: {str(e)}")
        return

    if response.status_code == 200:
        context.log(f"Uptime Kuma 通知发送成功 (状态码: {response.status_code})")
    else:
        context.log(f"Uptime Kuma 通知响应状态码非 200: {response.status_code}")


async def _resolve_backup_path(server_id: Optional[str], path: Optional[str]) -> Path:
    """
    Resolve the actual backup path based on server_id and path parameters

    The resolved path (symlinks followed) must stay inside the servers root
    — and, for ``path``, inside the server's data directory.

    Args:
        server_id: Optional server identifier
        path: Optional path within server (relative to data directory)

    Returns:
        Absolute path to backup
    """

    if not server_id and not path:
        # Backup entire servers directory
        return await async_fs.resolve(settings.server_path)

    if not server_id:
        raise ValueError("不能在未指定server_id的情况下指定路径")

    instance = docker_mc_manager.get_instance(server_id)
    try:
        project_path = await async_fs.resolve_inside(
            Path(settings.server_path), instance.get_project_path()
        )
        if not path:
            return project_path

        data_path = instance.get_data_path()
        return await async_fs.resolve_inside(
            data_path, data_path / path.lstrip("/")
        )
    except async_fs.PathOutsideBaseError as e:
        raise ValueError(f"备份路径越界，不在服务器目录内: {e}")


async def backup_cronjob(context: ExecutionContext):
    """
    Create a backup snapshot and optionally forget old snapshots.

    This cron job creates a backup using restic and can optionally
    clean up old snapshots based on retention policies.

    If the server-operation lock is currently held (by a restore or another
    backup), this run is skipped with a structured log entry. Skips also send
    a "skipped" Uptime Kuma notification when configured.
    """
    params = cast(BackupJobParams, context.params)
    start_time = time.time()

    lock_key = params.server_id if params.server_id else GLOBAL_LOCK_KEY

    holder = LockHolder(
        kind=ServerOperationKind.BACKUP,
        started_at=datetime.now(timezone.utc),
        user_id=None,
        description=f"定时备份（{lock_key}）",
    )

    try:
        async with server_operation_lock.try_acquire(lock_key, holder) as acquired:
            if not acquired:
                current = server_operation_lock.get_holder(lock_key)
                if current is not None:
                    current_kind = (
                        "备份"
                        if current.kind == ServerOperationKind.BACKUP
                        else "恢复"
                    )
                    skip_msg = (
                        f"跳过备份: 服务器 '{lock_key}' 被{current_kind}占用"
                        f" ({current.description}, 起始 {current.started_at.isoformat()})"
                    )
                else:
                    skip_msg = f"跳过备份: 服务器 '{lock_key}' 当前被占用"
                context.log(skip_msg)
                if params.uptimekuma_url and params.uptimekuma_url.strip():
                    running_time = time.time() - start_time
                    await _send_uptimekuma_notification(
                        context, params.uptimekuma_url, True, f"skipped: {skip_msg}", running_time
                    )
                return
            # Get snapshot service
            service = _get_snapshot_service()

            # Resolve backup path
            backup_path = await _resolve_backup_path(params.server_id, params.path)

            # Log backup start
            if params.server_id:
                if params.path:
                    context.log(
                        f"开始备份服务器 '{params.server_id}' 的路径 '{params.path}'"
                    )
                else:
                    context.log(f"开始备份服务器 '{params.server_id}'")
            else:
                context.log("开始备份所有服务器")

            # Verify backup path exists
            if not await aioos.path.exists(backup_path):
                raise RuntimeError(f"备份路径不存在: {backup_path}")

            # Create backup
            context.log(f"正在创建快照: {backup_path}")
            snapshot = await service.create_snapshot([backup_path])

            context.log(f"快照创建成功: {snapshot.short_id} ({snapshot.id})")
            if snapshot.summary:
                context.log(
                    f"备份统计: {snapshot.summary.total_files_processed} 个文件, "
                    f"{snapshot.summary.total_bytes_processed} 字节"
                )

            # Run forget if enabled
            if params.enable_forget:
                context.log("开始清理旧快照...")

                try:
                    await service.forget(
                        keep_last=params.keep_last,
                        keep_hourly=params.keep_hourly,
                        keep_daily=params.keep_daily,
                        keep_weekly=params.keep_weekly,
                        keep_monthly=params.keep_monthly,
                        keep_yearly=params.keep_yearly,
                        keep_tag=params.keep_tag,
                        keep_within=params.keep_within,
                        prune=params.prune,
                    )
                    context.log("旧快照清理完成")
                except Exception as e:
                    context.log(f"警告: 清理旧快照时出错: {str(e)}")
                    # Don't fail the entire job if forget fails

            # Final success message
            backup_desc = (
                f"服务器 '{params.server_id}'" if params.server_id else "所有服务器"
            )
            if params.server_id and params.path:
                backup_desc += f" 路径 '{params.path}'"

            context.log(f"备份任务完成: {backup_desc} -> 快照 {snapshot.short_id}")

            # Send Uptime Kuma notification for success if configured
            if params.uptimekuma_url and params.uptimekuma_url.strip():
                running_time = time.time() - start_time
                await _send_uptimekuma_notification(
                    context, params.uptimekuma_url, True, "OK", running_time
                )

    except Exception as e:
        error_msg = f"备份任务失败: {str(e)}"

        # Send Uptime Kuma notification for failure if configured
        if params.uptimekuma_url and params.uptimekuma_url.strip():
            running_time = time.time() - start_time
            await _send_uptimekuma_notification(
                context, params.uptimekuma_url, False, error_msg, running_time
            )

        raise
