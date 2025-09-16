"""
Dynamic configuration API router.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.models import UserPublic

from ..dependencies import get_current_user
from ..dynamic_config.manager import config_manager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/config",
    tags=["dynamic-config"],
    dependencies=[Depends(get_current_user)],  # All endpoints require authentication
)


class ConfigModuleInfo(BaseModel):
    """Information about a configuration module."""

    module_name: str
    schema_class: str
    version: str
    json_schema: Dict[str, Any]


class ConfigModuleList(BaseModel):
    """List of all configuration modules."""

    modules: Dict[str, ConfigModuleInfo]


class ConfigData(BaseModel):
    """Configuration data response."""

    module_name: str
    config_data: Dict[str, Any]
    schema_version: str


class ConfigUpdateRequest(BaseModel):
    """Request to update configuration."""

    config_data: Dict[str, Any]


class ConfigUpdateResponse(BaseModel):
    """Response after updating configuration."""

    success: bool
    message: str
    updated_config: Dict[str, Any]


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str


@router.get("/modules", response_model=ConfigModuleList)
async def list_all_modules(_: UserPublic = Depends(get_current_user)):
    """
    List all registered configuration modules with their schema information.

    Returns:
        Dictionary containing information about all registered configuration modules
    """
    try:
        all_schema_info = config_manager.get_all_schema_info()
        modules = {
            name: ConfigModuleInfo(**info) for name, info in all_schema_info.items()
        }
        return ConfigModuleList(modules=modules)
    except Exception as e:
        logger.error(f"Failed to list configuration modules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configuration modules: {str(e)}",
        )


@router.get("/modules/{module_name}", response_model=ConfigData)
async def get_module_config(
    module_name: str, _: UserPublic = Depends(get_current_user)
):
    """
    Get configuration data for a specific module.

    Args:
        module_name: Name of the configuration module

    Returns:
        Configuration data and metadata
    """
    try:
        config_instance = config_manager.get_config(module_name)
        schema_info = config_manager.get_schema_info(module_name)

        return ConfigData(
            module_name=module_name,
            config_data=config_instance.model_dump(),
            schema_version=schema_info["version"],
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration module '{module_name}' not found",
        )
    except Exception as e:
        logger.error(f"Failed to get configuration for module '{module_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configuration: {str(e)}",
        )


@router.put("/modules/{module_name}", response_model=ConfigUpdateResponse)
async def update_module_config(
    module_name: str,
    request: ConfigUpdateRequest,
    _: UserPublic = Depends(get_current_user),
):
    """
    Update configuration for a specific module.

    Args:
        module_name: Name of the configuration module
        request: New configuration data

    Returns:
        Updated configuration and success status
    """
    try:
        updated_config = await config_manager.update_config(
            module_name, request.config_data
        )

        return ConfigUpdateResponse(
            success=True,
            message=f"Configuration for module '{module_name}' updated successfully",
            updated_config=updated_config.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update configuration for module '{module_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}",
        )


@router.get("/modules/{module_name}/schema", response_model=ConfigModuleInfo)
async def get_module_schema(
    module_name: str, _: UserPublic = Depends(get_current_user)
):
    """
    Get schema information for a specific module.

    Args:
        module_name: Name of the configuration module

    Returns:
        Schema metadata including field descriptions
    """
    try:
        schema_info = config_manager.get_schema_info(module_name)
        return ConfigModuleInfo(**schema_info)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration module '{module_name}' not found",
        )
    except Exception as e:
        logger.error(f"Failed to get schema for module '{module_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve schema: {str(e)}",
        )


@router.post("/modules/{module_name}/reset", response_model=ConfigUpdateResponse)
async def reset_module_config(
    module_name: str, _: UserPublic = Depends(get_current_user)
):
    """
    Reset configuration for a module to default values.

    Args:
        module_name: Name of the configuration module to reset

    Returns:
        Reset configuration and success status
    """
    try:
        reset_config = await config_manager.reset_config(module_name)

        return ConfigUpdateResponse(
            success=True,
            message=f"Configuration for module '{module_name}' reset to defaults",
            updated_config=reset_config.model_dump(),
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration module '{module_name}' not found",
        )
    except Exception as e:
        logger.error(f"Failed to reset configuration for module '{module_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset configuration: {str(e)}",
        )


@router.get("/health", response_model=SuccessResponse)
async def config_health_check(_: UserPublic = Depends(get_current_user)):
    """
    Health check endpoint for the dynamic configuration system.

    Returns:
        Health status of the configuration system
    """
    try:
        # Simple check to see if the config manager is initialized
        config_manager.get_all_configs()
        return SuccessResponse(
            success=True, message="Dynamic configuration system is healthy"
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuration system not initialized",
        )
    except Exception as e:
        logger.error(f"Configuration system health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration system health check failed",
        )
