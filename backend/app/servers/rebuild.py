"""Server rebuild background task."""

from collections.abc import AsyncGenerator

from ..background_tasks import TaskProgress
from ..db.database import get_async_session
from ..minecraft import MCServerStatus, docker_mc_manager
from .configuration import ServerConfiguration, save_configuration_metadata
from .port_utils import check_port_conflicts, extract_ports_from_yaml


async def rebuild_server_task(
    server_id: str,
    configuration: ServerConfiguration,
) -> AsyncGenerator[TaskProgress]:
    """Apply configuration and its source before restoring the running intent."""
    instance = docker_mc_manager.get_instance(server_id)
    yaml_content = configuration.yaml_content

    # Step 1: Validate and check ports
    yield TaskProgress(progress=0, message="验证配置...")

    try:
        game_port, rcon_port = extract_ports_from_yaml(yaml_content)
    except Exception as e:
        raise RuntimeError(f"无效的 YAML 配置: {e}") from e

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

    if was_running or status == MCServerStatus.CREATED:
        yield TaskProgress(progress=15, message="下线服务器...")
        await instance.down()
        yield TaskProgress(progress=40, message="服务器已停止")
    else:
        yield TaskProgress(progress=40, message="服务器未运行，跳过停止步骤")

    # Step 3: Update compose file
    yield TaskProgress(progress=45, message="更新配置文件...")
    await instance.update_compose_file(yaml_content)
    yield TaskProgress(progress=60, message="配置文件已更新")

    if configuration.template_snapshot is not None:
        yield TaskProgress(progress=62, message="保存配置来源...")
        async with get_async_session() as db:
            await save_configuration_metadata(db, server_id, configuration)

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
