"""Server rebuild background task."""

from typing import AsyncGenerator

from ..background_tasks import TaskProgress
from ..minecraft import MCServerStatus, docker_mc_manager
from .port_utils import check_port_conflicts, extract_ports_from_yaml


async def rebuild_server_task(
    server_id: str,
    yaml_content: str,
) -> AsyncGenerator[TaskProgress, None]:
    """Background task to rebuild server with new configuration.

    Steps:
    1. Validate YAML and check port conflicts (0-10%)
    2. Stop server if running (10-40%)
    3. Update compose file (40-60%)
    4. Start server if was running (60-100%)

    Args:
        server_id: The server ID to rebuild
        yaml_content: The new YAML content for the compose file

    Yields:
        TaskProgress with progress updates

    Raises:
        RuntimeError: If validation fails or port conflicts detected
    """
    instance = docker_mc_manager.get_instance(server_id)

    # Step 1: Validate and check ports
    yield TaskProgress(progress=0, message="验证配置...")

    try:
        game_port, rcon_port = extract_ports_from_yaml(yaml_content)
    except Exception as e:
        raise RuntimeError(f"无效的 YAML 配置: {e}")

    yield TaskProgress(progress=5, message="检查端口冲突...")

    conflicts = await check_port_conflicts(
        game_port, rcon_port, exclude_server_id=server_id
    )
    if conflicts:
        raise RuntimeError(f"端口冲突: {'; '.join(conflicts)}")

    yield TaskProgress(progress=10, message="获取服务器状态...")

    # Step 2: Check status and stop if needed
    status = await instance.get_status()
    was_running = status in [
        MCServerStatus.RUNNING,
        MCServerStatus.STARTING,
        MCServerStatus.HEALTHY,
    ]

    if was_running:
        yield TaskProgress(progress=15, message="停止服务器...")
        await instance.down()
        yield TaskProgress(progress=40, message="服务器已停止")
    else:
        yield TaskProgress(progress=40, message="服务器未运行，跳过停止步骤")

    # Step 3: Update compose file
    yield TaskProgress(progress=45, message="更新配置文件...")
    await instance.update_compose_file(yaml_content)
    yield TaskProgress(progress=60, message="配置文件已更新")

    # Step 4: Restart if was running
    if was_running:
        yield TaskProgress(progress=65, message="启动服务器...")
        await instance.up()
        yield TaskProgress(progress=100, message="服务器已启动")
    else:
        yield TaskProgress(progress=100, message="配置更新完成")

    yield TaskProgress(
        progress=100,
        message="配置更新完成",
        result={
            "game_port": game_port,
            "rcon_port": rcon_port,
            "was_running": was_running,
        },
    )
