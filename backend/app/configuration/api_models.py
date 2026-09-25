from typing import Any

from pydantic import BaseModel

from app.templates import VariableDefinition


class ComposeConfig(BaseModel):
    yaml_content: str
    expected_version: str | None = None


class RebuildResponse(BaseModel):
    task_id: str


class TemplateConfigResponse(BaseModel):
    """Response model for template configuration."""

    server_id: str
    template_id: int
    template_name: str
    yaml_template: str
    variable_definitions: list[VariableDefinition]
    variable_values: dict[str, Any]
    json_schema: dict
    snapshot_time: str
    has_template_update: bool = False
    template_deleted: bool = False
    version: str


class TemplateConfigUpdateRequest(BaseModel):
    """Request model for updating template configuration."""

    variable_values: dict[str, Any]
    expected_version: str | None = None


class TemplateConfigUpdateResponse(BaseModel):
    """Response model for template configuration update."""

    task_id: str


class TemplateConfigPreviewResponse(BaseModel):
    """Response model for template configuration preview."""

    is_template_based: bool
    template_id: int | None


class ConvertToDirectResponse(BaseModel):
    """Response model for converting to direct mode."""

    success: bool


class ConvertToDirectRequest(BaseModel):
    expected_version: str | None = None


class ExtractVariablesRequest(BaseModel):
    """Request model for extracting variables."""

    template_id: int


class ExtractVariablesResponse(BaseModel):
    """Response model for extracted variables."""

    extracted_values: dict[str, Any]
    warnings: list[str]
    json_schema: dict
    variable_definitions: list[VariableDefinition]
    current_compose: str
    rendered_compose: str
    version: str


class ConvertToTemplateRequest(BaseModel):
    """Request model for converting to template mode."""

    template_id: int
    variable_values: dict[str, Any]
    expected_version: str | None = None


class ConvertToTemplateResponse(BaseModel):
    """Response model for converting to template mode."""

    task_id: str | None = None
    skipped_rebuild: bool = False


class CheckConversionRequest(BaseModel):
    """Request model for checking if conversion requires rebuild."""

    template_id: int
    variable_values: dict[str, Any]


class CheckConversionResponse(BaseModel):
    """Response model for conversion rebuild check."""

    requires_rebuild: bool
    version: str
