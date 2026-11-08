"""Typed runtime configuration with persisted structure versions."""

import hashlib
import json

from pydantic import BaseModel
from pydantic_core import PydanticUndefined


class BaseConfigSchema(BaseModel):
    """Configuration validation and persisted structure-version identity."""

    def validate_update(self) -> None:
        """Validate newly submitted settings without changing legacy loading rules."""

    @classmethod
    def get_schema_version(cls) -> str:
        """
        Generate a version hash based on the model's field structure.

        This creates a unique version identifier that changes when:
        - Fields are added or removed
        - Field types are changed
        - Field default values are changed

        Returns:
            SHA256 hash of the model structure as version string
        """
        # Get model fields and their types/defaults
        fields_info = {}
        for field_name, field_info in cls.model_fields.items():
            # Handle undefined defaults properly
            default_str = None
            if field_info.default is not PydanticUndefined:
                default_str = str(field_info.default)

            fields_info[field_name] = {
                "annotation": str(field_info.annotation),
                "default": default_str,
                "required": field_info.is_required(),
            }

        # Create deterministic hash
        version_data = json.dumps(fields_info, sort_keys=True)
        return hashlib.sha256(version_data.encode()).hexdigest()[:16]
