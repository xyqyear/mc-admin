import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager
from ...minecraft.compose import MCComposeFile
from ...minecraft.docker.compose_file import ComposeFile
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["server-creation"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


class CreateServerRequest(BaseModel):
    yaml_content: str


# Helper functions for port conflict checking
def extract_ports_from_yaml(yaml_content: str) -> tuple[int, int]:
    """Extract game port and RCON port from YAML content.
    
    Args:
        yaml_content: Docker Compose YAML content
        
    Returns:
        tuple[int, int]: (game_port, rcon_port)
        
    Raises:
        ValueError: If YAML is invalid or doesn't contain required ports
    """
    try:
        # Parse YAML and create compose objects
        compose_dict = yaml.safe_load(yaml_content)
        compose_file = ComposeFile.from_dict(compose_dict)
        mc_compose = MCComposeFile(compose_file)
        
        # Extract ports using existing methods
        game_port = mc_compose.get_game_port()
        rcon_port = mc_compose.get_rcon_port()
        
        return game_port, rcon_port
    except Exception as e:
        raise ValueError(f"Failed to extract ports from YAML: {str(e)}")


async def check_port_conflicts(game_port: int, rcon_port: int) -> list[str]:
    """Check for port conflicts with existing servers.
    
    Args:
        game_port: Game port to check
        rcon_port: RCON port to check
        
    Returns:
        list[str]: List of conflict messages, empty if no conflicts
    """
    conflicts = []
    
    try:
        # Get all existing instances
        instances = await mc_manager.get_all_instances()
        
        for instance in instances:
            try:
                # Get compose file path to check if server exists
                compose_file_path = await instance.get_compose_file_path()
                if compose_file_path is None:
                    # Server doesn't have compose file yet, skip
                    continue
                
                # Parse compose file directly to get port information
                compose_content = await instance.get_compose_file()
                existing_game_port, existing_rcon_port = extract_ports_from_yaml(compose_content)
                
                # Check game port conflict
                if existing_game_port == game_port:
                    conflicts.append(
                        f"Game port {game_port} is already used by server '{instance.get_name()}'"
                    )
                
                # Check RCON port conflict
                if existing_rcon_port == rcon_port:
                    conflicts.append(
                        f"RCON port {rcon_port} is already used by server '{instance.get_name()}'"
                    )
                    
            except Exception:
                # If we can't parse this server's ports, skip it
                continue
                
    except Exception as e:
        # If we can't get instances, that's a more serious error
        raise HTTPException(status_code=500, detail=f"Failed to check port conflicts: {str(e)}")
    
    return conflicts


@router.post("/{server_id}")
async def create_server(
    server_id: str,
    create_request: CreateServerRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new Minecraft server with the provided Docker Compose configuration"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server already exists
        if await instance.exists():
            raise HTTPException(
                status_code=409, detail=f"Server '{server_id}' already exists"
            )

        # Extract ports from YAML to check for conflicts
        try:
            game_port, rcon_port = extract_ports_from_yaml(create_request.yaml_content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check for port conflicts with existing servers
        port_conflicts = await check_port_conflicts(game_port, rcon_port)
        if port_conflicts:
            conflict_messages = "; ".join(port_conflicts)
            raise HTTPException(
                status_code=409, 
                detail=f"Port conflicts detected: {conflict_messages}"
            )

        # Create the server using the MCInstance.create method
        await instance.create(create_request.yaml_content)

        return {
            "message": f"Server '{server_id}' created successfully",
            "game_port": game_port,
            "rcon_port": rcon_port
        }

    except HTTPException:
        raise
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create server: {str(e)}")