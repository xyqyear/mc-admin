import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from ...config import settings
from ...minecraft import docker_mc_manager
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, success


@dataclass(frozen=True)
class PermissionScanResult:
    root_uid: int | None
    mismatched: int
    samples: list[dict[str, object]]
    truncated: bool
    errors: list[str]


async def scan_permission_owner_with_fd(root: Path, limit: int) -> PermissionScanResult:
    try:
        root_stat = await asyncio.to_thread(root.stat, follow_symlinks=False)
    except OSError as exc:
        return PermissionScanResult(
            root_uid=None,
            mismatched=0,
            samples=[],
            truncated=False,
            errors=[f"{root}: {exc}"],
        )

    cmd = [
        str(settings.fd_binary_path),
        "--unrestricted",
        "--absolute-path",
        "--print0",
        "--owner",
        f"!{root_stat.st_uid}",
        "--max-results",
        str(limit + 1),
        "",
        str(root),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return PermissionScanResult(
            root_uid=root_stat.st_uid,
            mismatched=0,
            samples=[],
            truncated=False,
            errors=[f"fd command not found at {settings.fd_binary_path}"],
        )

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        return PermissionScanResult(
            root_uid=root_stat.st_uid,
            mismatched=0,
            samples=[],
            truncated=False,
            errors=[detail or f"fd exited with status {proc.returncode}"],
        )

    mismatch_paths = [raw for raw in stdout.split(b"\0") if raw]
    truncated = len(mismatch_paths) > limit
    mismatch_paths = mismatch_paths[:limit]

    samples: list[dict[str, object]] = []
    errors: list[str] = []
    for raw_path in mismatch_paths[:10]:
        path = Path(os.fsdecode(raw_path))
        sample: dict[str, object] = {"path": str(path)}
        try:
            path_stat = await asyncio.to_thread(path.stat, follow_symlinks=False)
            sample["uid"] = path_stat.st_uid
        except OSError as exc:
            errors.append(f"{path}: {exc}")
        samples.append(sample)

    return PermissionScanResult(
        root_uid=root_stat.st_uid,
        mismatched=len(mismatch_paths),
        samples=samples,
        truncated=truncated,
        errors=errors,
    )


async def check_permission_consistency(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["files.permission_consistency"]
    active_servers = await context.active_servers()
    if not active_servers:
        return success(definition, "没有需要检查文件所有者的运行中服务器。")

    findings: list[SelfCheckFindingResult] = []
    for server in active_servers:
        root = docker_mc_manager.get_instance(server.server_id).get_project_path()
        if not root.exists():
            findings.append(
                finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="warning",
                    status="warning",
                    title=definition.title,
                    message="服务器项目目录不存在。",
                    server_id=server.server_id,
                    evidence={"path": str(root)},
                )
            )
            continue

        scan = await scan_permission_owner_with_fd(
            root,
            context.config.permission_scan_max_entries,
        )
        if scan.mismatched:
            findings.append(
                finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="warning",
                    status="warning",
                    title=definition.title,
                    message="部分服务器文件的所有者 UID 与服务器根目录不同。",
                    server_id=server.server_id,
                    evidence={
                        "root": str(root),
                        "root_uid": scan.root_uid,
                        "mismatched": scan.mismatched,
                        "samples": scan.samples,
                        "truncated": scan.truncated,
                        "errors": scan.errors[:10],
                    },
                    remediation=["统一该服务器目录下文件的所有者 UID。"],
                )
            )
        elif scan.errors:
            findings.append(
                finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="warning",
                    status="warning",
                    title=definition.title,
                    message="文件所有者 UID 扫描失败。",
                    server_id=server.server_id,
                    evidence={"root": str(root), "errors": scan.errors[:10]},
                )
            )

    if not findings:
        return success(definition, "服务器文件的所有者 UID 与服务器根目录一致。")
    return findings


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "files.permission_consistency",
            "files",
            "文件所有者一致性",
            "检查服务器文件的所有者 UID 是否与服务器根目录一致。",
            check_permission_consistency,
        ),
    ]
}


_scan_permission_owner_with_fd = scan_permission_owner_with_fd
_check_permission_consistency = check_permission_consistency
