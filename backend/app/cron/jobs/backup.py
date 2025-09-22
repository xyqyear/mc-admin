import time
from pathlib import Path
from typing import Annotated, List, Optional, cast

import requests
from pydantic import Field, field_validator, model_validator

from ...config import settings
from ...dynamic_config.schemas import BaseConfigSchema
from ...minecraft import DockerMCManager
from ...snapshots import ResticManager
from ..types import ExecutionContext


class BackupJobParams(BaseConfigSchema):
    """Parameters for backup cron job"""

    # Backup target configuration
    server_id: Annotated[
        Optional[str],
        Field(description="可选要备份的服务器 (None = 备份所有服务器)"),
    ] = None
    path: Annotated[Optional[str], Field(description="服务器数据目录内的可选路径")] = (
        None
    )

    # Forget configuration
    enable_forget: Annotated[bool, Field(description="是否在备份后运行 forget")] = True

    # Forget retention policies (all optional, but at least one must be specified if enable_forget=True)
    keep_last: Annotated[Optional[int], Field(description="保留最近的 n 个快照")] = None
    keep_hourly: Annotated[
        Optional[int], Field(description="在最近 n 小时内每小时保留一次")
    ] = None
    keep_daily: Annotated[
        Optional[int], Field(description="在最近 n 天内每天保留一次")
    ] = None
    keep_weekly: Annotated[
        Optional[int], Field(description="在最近 n 周内每周保留一次")
    ] = None
    keep_monthly: Annotated[
        Optional[int], Field(description="在最近 n 月内每月保留一次")
    ] = None
    keep_yearly: Annotated[
        Optional[int], Field(description="在最近 n 年内每年保留一次")
    ] = None
    keep_tag: Annotated[
        Optional[List[str]],
        Field(description="保留带有这些标签的所有快照"),
    ] = None
    keep_within: Annotated[
        Optional[str],
        Field(description='在指定时长内保留所有快照 (例如 "4d", "2y5m7d3h")'),
    ] = None

    # Forget options
    prune: Annotated[
        bool, Field(description="是否在 forget 后运行 prune (默认 True)")
    ] = True

    # Uptime Kuma integration
    uptimekuma_url: Annotated[
        Optional[str], Field(description="Uptime Kuma 推送监控 URL (可选)")
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


def _get_restic_manager() -> ResticManager:
    """Get configured restic manager instance"""
    if not settings.restic:
        raise RuntimeError("Restic未配置。请在config.toml中添加restic设置")

    return ResticManager(
        repository_path=settings.restic.repository_path,
        password=settings.restic.password,
    )


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
    try:
        context.log(f"发送 Uptime Kuma 通知到: {uptimekuma_url}")

        # Uptime Kuma push monitor parameters
        params = {
            "status": "up" if ok else "down",
            "msg": msg,
            "ping": int(ping * 1000),  # Convert to milliseconds
        }

        # Send GET request to Uptime Kuma
        response = requests.get(uptimekuma_url, params=params, timeout=30)

        if response.status_code == 200:
            context.log(f"Uptime Kuma 通知发送成功 (状态码: {response.status_code})")
        else:
            context.log(f"Uptime Kuma 通知响应状态码非 200: {response.status_code}")

    except requests.RequestException as e:
        context.log(f"发送 Uptime Kuma 通知失败: {str(e)}")
    except Exception as e:
        context.log(f"Uptime Kuma 通知时发生未知错误: {str(e)}")


def _resolve_backup_path(server_id: Optional[str], path: Optional[str]) -> Path:
    """
    Resolve the actual backup path based on server_id and path parameters

    Args:
        server_id: Optional server identifier
        path: Optional path within server (relative to data directory)

    Returns:
        Absolute path to backup
    """

    mc_manager = DockerMCManager(settings.server_path)

    if not server_id and not path:
        # Backup entire servers directory
        return settings.server_path.resolve()
    elif server_id and not path:
        # Backup specific server directory
        instance = mc_manager.get_instance(server_id)
        return instance.get_project_path().resolve()
    elif server_id and path:
        # Backup specific path within server's data directory
        instance = mc_manager.get_instance(server_id)
        data_path = instance.get_data_path()
        target_path = data_path / path.lstrip("/")
        return target_path.resolve()
    else:
        raise ValueError("不能在未指定server_id的情况下指定路径")


async def backup_cronjob(context: ExecutionContext):
    """
    Create a backup snapshot and optionally forget old snapshots.

    This cron job creates a backup using restic and can optionally
    clean up old snapshots based on retention policies.
    """
    params = cast(BackupJobParams, context.params)
    start_time = time.time()

    try:
        # Get restic manager
        restic_manager = _get_restic_manager()

        # Resolve backup path
        backup_path = _resolve_backup_path(params.server_id, params.path)

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
        if not backup_path.exists():
            raise RuntimeError(f"备份路径不存在: {backup_path}")

        # Create backup
        context.log(f"正在创建快照: {backup_path}")
        snapshot = await restic_manager.backup(backup_path)

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
                await restic_manager.forget(
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
