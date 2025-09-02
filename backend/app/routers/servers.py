import asyncio
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_current_user, get_websocket_user
from ..minecraft import DockerMCManager, MCInstance, MCServerStatus
from ..models import User
from ..websocket.console import ConsoleWebSocketHandler

router = APIRouter(
    prefix="/servers",
    tags=["servers"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


# Pydantic models for API responses
class ServerInfo(BaseModel):
    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    maxMemoryBytes: int
    rconPort: int


class ServerStatus(BaseModel):
    status: MCServerStatus


class ServerResources(BaseModel):
    cpuPercentage: float
    memoryUsageBytes: int


class ServerPlayers(BaseModel):
    onlinePlayers: list[str]


class ServerListItem(BaseModel):
    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    status: MCServerStatus
    onlinePlayers: list[str]
    maxMemoryBytes: int
    rconPort: int
    cpuPercentage: Optional[float] = None
    memoryUsageBytes: Optional[int] = None
    diskUsageBytes: Optional[int] = None
    diskTotalBytes: Optional[int] = None
    diskAvailableBytes: Optional[int] = None


class ServerIOStats(BaseModel):
    # Disk I/O statistics
    diskReadBytes: int
    diskWriteBytes: int
    # Network I/O statistics
    networkReceiveBytes: int
    networkSendBytes: int
    # Disk usage and space information
    diskUsageBytes: int
    diskTotalBytes: int
    diskAvailableBytes: int


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down


class ComposeConfig(BaseModel):
    yaml_content: str


class RconCommand(BaseModel):
    command: str


class FileItem(BaseModel):
    name: str
    type: str  # 'file' or 'directory'
    size: int
    modified_at: str
    is_config: bool
    is_editable: bool
    path: str


class FileListResponse(BaseModel):
    items: List[FileItem]
    current_path: str


class FileContent(BaseModel):
    content: str


class CreateFileRequest(BaseModel):
    name: str
    type: str  # 'file' or 'directory'
    path: str


class RenameFileRequest(BaseModel):
    old_path: str
    new_name: str


# Helper functions for file management


def _get_server_data_path(instance: MCInstance) -> Path:
    """Get the data directory path for a server instance."""
    return instance.get_project_path() / "data"


def _is_config_file(file_path: Path) -> bool:
    """Determine if a file is a configuration file based on extension."""
    config_extensions = {
        ".yml",
        ".yaml",
        ".properties",
        ".json",
        ".toml",
        ".conf",
        ".cfg",
        ".txt",
        ".log",
    }
    return file_path.suffix.lower() in config_extensions


def _is_editable_file(file_path: Path) -> bool:
    """Determine if a file is editable based on extension and type."""
    editable_extensions = {
        ".yml",
        ".yaml",
        ".properties",
        ".json",
        ".toml",
        ".conf",
        ".cfg",
        ".txt",
        ".log",
    }
    return file_path.suffix.lower() in editable_extensions and file_path.is_file()


def _get_file_items(base_path: Path, current_path: str = "/") -> List[FileItem]:
    """Get list of files and directories in the specified path."""
    if current_path.startswith("/"):
        current_path = current_path[1:]  # Remove leading slash

    actual_path = base_path / current_path if current_path else base_path

    if not actual_path.exists() or not actual_path.is_dir():
        return []

    items = []

    try:
        for item in actual_path.iterdir():
            relative_path = item.relative_to(base_path)
            file_path = "/" + str(relative_path).replace("\\", "/")

            if item.is_file():
                size = item.stat().st_size
                file_type = "file"
            else:
                size = 0
                file_type = "directory"

            modified_at = item.stat().st_mtime
            modified_at_str = f"{modified_at:.0f}"  # Unix timestamp as string

            is_config = _is_config_file(item) if item.is_file() else False
            is_editable = _is_editable_file(item)

            items.append(
                FileItem(
                    name=item.name,
                    type=file_type,
                    size=size,
                    modified_at=modified_at_str,
                    is_config=is_config,
                    is_editable=is_editable,
                    path=file_path,
                )
            )
    except PermissionError:
        # Handle permission errors gracefully
        pass

    # Sort items: directories first, then files, both alphabetically
    items.sort(key=lambda x: (x.type == "file", x.name.lower()))

    return items


# API Endpoints


@router.get("/", response_model=list[ServerListItem])
async def get_servers(_: str = Depends(get_current_user)):
    """Get list of all servers with their basic info and current status"""
    try:
        # Get all server instances
        instances = await mc_manager.get_all_instances()

        if not instances:
            return []

        # Gather all server data concurrently
        server_data_tasks = [_get_server_list_item(instance) for instance in instances]

        servers = await asyncio.gather(*server_data_tasks, return_exceptions=True)

        # Filter out any exceptions and return valid servers
        valid_servers = [
            server for server in servers if not isinstance(server, Exception)
        ]

        return valid_servers

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get servers: {str(e)}")


@router.get("/{server_id}", response_model=ServerInfo)
async def get_server(server_id: str, _: str = Depends(get_current_user)):
    """Get detailed information about a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get server info
        server_info = await instance.get_server_info()

        return ServerInfo(
            id=server_id,
            name=server_info.name,
            serverType=server_info.server_type or "vanilla",
            gameVersion=server_info.game_version or "latest",
            gamePort=server_info.game_port or 25565,
            maxMemoryBytes=server_info.max_memory_bytes or 2147483648,  # 2GB default
            rconPort=server_info.rcon_port
            or 25575,  # Use real RCON port from compose file
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server info: {str(e)}"
        )


@router.get("/{server_id}/status", response_model=ServerStatus)
async def get_server_status(server_id: str, _: str = Depends(get_current_user)):
    """Get current status of a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)
        status = await instance.get_status()

        return ServerStatus(status=status)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server status: {str(e)}"
        )


@router.get("/{server_id}/resources", response_model=ServerResources)
async def get_server_resources(server_id: str, _: str = Depends(get_current_user)):
    """Get system resource information for a specific server (available when running/starting/healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where resource monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' resources not available (status: {status})",
            )

        # Get resource data concurrently
        cpu_task = instance.get_cpu_percentage()
        memory_task = instance.get_memory_usage()

        cpu_percentage, memory_stats = await asyncio.gather(cpu_task, memory_task)

        # Calculate actual memory usage from memory stats (anon + file is commonly used memory)
        memory_usage_bytes = memory_stats.anon + memory_stats.file

        return ServerResources(
            cpuPercentage=cpu_percentage,
            memoryUsageBytes=memory_usage_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server resources: {str(e)}"
        )


@router.get("/{server_id}/players", response_model=ServerPlayers)
async def get_server_players(server_id: str, _: str = Depends(get_current_user)):
    """Get online players for a specific server (only available when healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is healthy (required for player list)
        status = await instance.get_status()
        if status != MCServerStatus.HEALTHY:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' players not available - server must be healthy (current status: {status})",
            )

        # Get player list
        players = await instance.list_players()

        return ServerPlayers(
            onlinePlayers=players,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server players: {str(e)}"
        )


@router.get("/{server_id}/iostats", response_model=ServerIOStats)
async def get_server_iostats(server_id: str, _: str = Depends(get_current_user)):
    """Get comprehensive I/O statistics for a specific server (disk I/O, network I/O, disk usage)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where I/O monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' I/O stats not available (status: {status})",
            )

        # Get I/O statistics concurrently
        disk_io_task = instance.get_disk_io()
        network_io_task = instance.get_network_io()
        disk_space_task = instance.get_disk_space_info()

        disk_io, network_io, disk_space = await asyncio.gather(
            disk_io_task, network_io_task, disk_space_task
        )

        return ServerIOStats(
            diskReadBytes=disk_io.total_read_bytes,
            diskWriteBytes=disk_io.total_write_bytes,
            networkReceiveBytes=network_io.total_rx_bytes,
            networkSendBytes=network_io.total_tx_bytes,
            diskUsageBytes=disk_space.used_bytes,
            diskTotalBytes=disk_space.total_bytes,
            diskAvailableBytes=disk_space.available_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server I/O stats: {str(e)}"
        )


@router.get("/{server_id}/compose")
async def get_server_compose(server_id: str, _: str = Depends(get_current_user)):
    """Get the Docker Compose configuration for a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get compose file content
        compose_content = await instance.get_compose_file()

        return {"yaml_content": compose_content}

    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Compose file not found for server '{server_id}'"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get compose configuration: {str(e)}"
        )


@router.post("/{server_id}/compose")
async def update_server_compose(
    server_id: str, compose_config: ComposeConfig, _: str = Depends(get_current_user)
):
    """Update the Docker Compose configuration for a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get current server status
        status = await instance.get_status()

        # If server is running, stop it first
        server_was_running = False
        if status in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            server_was_running = True
            await instance.down()

        try:
            # Update the compose file
            await instance.update_compose_file(compose_config.yaml_content)

            # If server was running, start it again
            if server_was_running:
                await instance.up()

            return {
                "message": f"Server '{server_id}' compose configuration updated successfully"
            }

        except Exception as e:
            # If something goes wrong and server was running, try to start it again with the original config
            if server_was_running:
                try:
                    await instance.up()
                except Exception:
                    pass  # Best effort to restart
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update compose configuration: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update compose configuration: {str(e)}"
        )


@router.post("/{server_id}/operations")
async def server_operation(
    server_id: str, operation: ServerOperation, _: str = Depends(get_current_user)
):
    """Perform operations on a server (start, stop, restart, up, down)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        action = operation.action.lower()

        if action == "start":
            await instance.start()
        elif action == "stop":
            await instance.stop()
        elif action == "restart":
            await instance.restart()
        elif action == "up":
            await instance.up()
        elif action == "down":
            await instance.down()
        elif action == "remove":
            await instance.remove()
        else:
            raise HTTPException(status_code=400, detail=f"Invalid operation: {action}")

        return {"message": f"Server '{server_id}' {action} operation completed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operation failed: {str(e)}")


@router.post("/{server_id}/rcon")
async def send_rcon_command(
    server_id: str, rcon_command: RconCommand, _: str = Depends(get_current_user)
):
    """Send RCON command to a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists and is healthy
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        status = await instance.get_status()
        if status != MCServerStatus.HEALTHY:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' must be healthy to send RCON commands (current status: {status})",
            )

        # Send RCON command
        result = await instance.send_command_rcon(rcon_command.command)

        return {"result": result, "command": rcon_command.command}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send RCON command: {str(e)}"
        )


# File Management Endpoints


@router.get("/{server_id}/files", response_model=FileListResponse)
async def list_files(
    server_id: str, path: str = "/", _: str = Depends(get_current_user)
):
    """List files and directories in the specified server path"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        items = _get_file_items(base_path, path)

        return FileListResponse(items=items, current_path=path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/{server_id}/files/content")
async def get_file_content(
    server_id: str, path: str, _: str = Depends(get_current_user)
):
    """Get content of a specific file"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        file_path = base_path / path.lstrip("/")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Check if file is editable
        if not _is_editable_file(file_path):
            raise HTTPException(status_code=400, detail="File is not editable")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="latin1") as f:
                    content = f.read()
            except Exception:
                raise HTTPException(
                    status_code=400, detail="Unable to read file as text"
                )

        return FileContent(content=content)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.post("/{server_id}/files/content")
async def update_file_content(
    server_id: str,
    path: str,
    file_content: FileContent,
    _: str = Depends(get_current_user),
):
    """Update content of a specific file"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        file_path = base_path / path.lstrip("/")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Check if file is editable
        if not _is_editable_file(file_path):
            raise HTTPException(status_code=400, detail="File is not editable")

        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")
        shutil.copy2(file_path, backup_path)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content.content)
        except Exception as e:
            # Restore from backup if write fails
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
            raise e
        finally:
            # Clean up backup
            if backup_path.exists():
                backup_path.unlink()

        return {"message": "File updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")


@router.get("/{server_id}/files/download")
async def download_file(server_id: str, path: str, _: str = Depends(get_current_user)):
    """Download a specific file"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        file_path = base_path / path.lstrip("/")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to download file: {str(e)}"
        )


@router.post("/{server_id}/files/upload")
async def upload_file(
    server_id: str,
    path: str = "/",
    file: UploadFile = File(...),
    _: str = Depends(get_current_user),
):
    """Upload a file to the specified server path"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        target_dir = base_path / path.lstrip("/")

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        if not target_dir.is_dir():
            raise HTTPException(
                status_code=400, detail="Target path is not a directory"
            )

        file_path = target_dir / (file.filename or "unnamed_file")

        # Check if file already exists
        if file_path.exists():
            raise HTTPException(status_code=409, detail="File already exists")

        # Write file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        return {"message": f"File '{file.filename}' uploaded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post("/{server_id}/files/create")
async def create_file_or_directory(
    server_id: str,
    create_request: CreateFileRequest,
    _: str = Depends(get_current_user),
):
    """Create a new file or directory"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        target_path = base_path / create_request.path.lstrip("/") / create_request.name

        # Check if already exists
        if target_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"{'Directory' if create_request.type == 'directory' else 'File'} already exists",
            )

        # Create parent directories if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if create_request.type == "directory":
            target_path.mkdir()
            message = f"Directory '{create_request.name}' created successfully"
        elif create_request.type == "file":
            target_path.touch()
            message = f"File '{create_request.name}' created successfully"
        else:
            raise HTTPException(
                status_code=400, detail="Invalid type. Must be 'file' or 'directory'"
            )

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create {'directory' if create_request.type == 'directory' else 'file'}: {str(e)}",
        )


@router.delete("/{server_id}/files")
async def delete_file_or_directory(
    server_id: str, path: str, _: str = Depends(get_current_user)
):
    """Delete a file or directory"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        target_path = base_path / path.lstrip("/")

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        if target_path.is_file():
            target_path.unlink()
            message = f"File '{target_path.name}' deleted successfully"
        elif target_path.is_dir():
            shutil.rmtree(target_path)
            message = f"Directory '{target_path.name}' deleted successfully"
        else:
            raise HTTPException(status_code=400, detail="Invalid path")

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


@router.post("/{server_id}/files/rename")
async def rename_file_or_directory(
    server_id: str,
    rename_request: RenameFileRequest,
    _: str = Depends(get_current_user),
):
    """Rename a file or directory"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        old_path = base_path / rename_request.old_path.lstrip("/")
        new_path = old_path.parent / rename_request.new_name

        if not old_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        if new_path.exists():
            raise HTTPException(status_code=409, detail="Target name already exists")

        old_path.rename(new_path)

        item_type = "Directory" if new_path.is_dir() else "File"
        return {"message": f"{item_type} renamed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename: {str(e)}")


@router.websocket("/{server_id}/console")
async def console_websocket(
    websocket: WebSocket, server_id: str, user: User = Depends(get_websocket_user)
):
    instance = mc_manager.get_instance(server_id)
    handler = ConsoleWebSocketHandler(websocket, instance)
    await handler.handle_connection(server_id)


# Helper function
async def _get_server_list_item(instance: MCInstance) -> ServerListItem:
    """Helper to get server list item data for a single instance"""
    try:
        server_id = instance.get_name()

        # Get basic info and status concurrently
        info_task = instance.get_server_info()
        status_task = instance.get_status()

        server_info, status = await asyncio.gather(info_task, status_task)

        # Initialize with basic data
        list_item = ServerListItem(
            id=server_id,
            name=server_info.name,
            serverType=server_info.server_type or "vanilla",
            gameVersion=server_info.game_version or "latest",
            gamePort=server_info.game_port or 25565,
            status=status,
            onlinePlayers=[],
            maxMemoryBytes=server_info.max_memory_bytes or 2147483648,
            rconPort=server_info.rcon_port
            or 25575,  # Use real RCON port from compose file
        )

        # Get resource data if server is in a state where resource monitoring is available
        if status in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            try:
                cpu_task = instance.get_cpu_percentage()
                memory_task = instance.get_memory_usage()

                cpu_percentage, memory_stats = await asyncio.gather(
                    cpu_task, memory_task, return_exceptions=True
                )

                # Update resource data if successful
                if not isinstance(cpu_percentage, BaseException):
                    list_item.cpuPercentage = cpu_percentage
                if not isinstance(memory_stats, BaseException):
                    list_item.memoryUsageBytes = memory_stats.anon + memory_stats.file

            except Exception:
                # Resource data is optional, continue without it
                pass

        # Get disk space information for any server that exists (doesn't require running state)
        try:
            disk_space = await instance.get_disk_space_info()
            list_item.diskUsageBytes = disk_space.used_bytes
            list_item.diskTotalBytes = disk_space.total_bytes
            list_item.diskAvailableBytes = disk_space.available_bytes
        except Exception:
            # Disk space information is optional, continue without it
            pass

        # Get player data only if server is healthy
        if status == MCServerStatus.HEALTHY:
            try:
                players = await instance.list_players()
                list_item.onlinePlayers = players
            except Exception:
                # Player data is optional, continue without it
                pass

        return list_item

    except Exception as e:
        # Log error but don't fail the entire request
        print(f"Error getting server list item for {instance.get_name()}: {e}")
        # Return minimal data
        return ServerListItem(
            id=instance.get_name(),
            name=instance.get_name(),
            serverType="unknown",
            gameVersion="unknown",
            gamePort=25565,
            status=MCServerStatus.REMOVED,
            onlinePlayers=[],
            maxMemoryBytes=2147483648,
            rconPort=25575,  # Default RCON port
        )
