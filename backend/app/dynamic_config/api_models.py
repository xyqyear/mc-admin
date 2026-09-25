from typing import Any

from pydantic import BaseModel


class ConfigModuleInfo(BaseModel):
    """Information about a configuration module."""

    module_name: str
    schema_class: str
    version: str
    json_schema: dict[str, Any]


class ConfigModuleList(BaseModel):
    """List of all configuration modules."""

    modules: dict[str, ConfigModuleInfo]


class ConfigData(BaseModel):
    """Configuration data response."""

    module_name: str
    config_data: dict[str, Any]
    schema_version: str


class ConfigUpdateRequest(BaseModel):
    """Request to update configuration."""

    config_data: dict[str, Any]


class ConfigUpdateResponse(BaseModel):
    """Response after updating configuration."""

    success: bool
    message: str
    updated_config: dict[str, Any]
