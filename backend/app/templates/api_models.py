from pydantic import BaseModel

from app.templates import VariableDefinition


class DefaultVariablesResponse(BaseModel):
    """Response model for default variables."""

    variable_definitions: list[VariableDefinition]


class DefaultVariablesUpdateRequest(BaseModel):
    """Request model for updating default variables."""

    variable_definitions: list[VariableDefinition]
