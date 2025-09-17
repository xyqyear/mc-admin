"""
Dynamic configuration schemas with support for nested models and deprecated fields.
"""

import hashlib
import json
import types
from typing import Union, get_args, get_origin

from pydantic import BaseModel, model_validator
from pydantic_core import PydanticUndefined


class BaseConfigSchema(BaseModel):
    """
    Base class for all dynamic configuration schemas.

    Provides version management, field metadata extraction, and deprecated field handling.
    """

    @model_validator(mode="before")
    @classmethod
    def _validate_union_fields(cls, values):
        """Validate that Union fields follow discriminated union conventions."""
        for field_name, field_info in cls.model_fields.items():
            origin = get_origin(field_info.annotation)

            # Check if this field is a Union
            if origin in (Union, types.UnionType):
                args = get_args(field_info.annotation)
                non_none_args = [arg for arg in args if arg is not type(None)]

                # Skip optional fields (Union[Type, None])
                if len(non_none_args) <= 1:
                    continue

                # Check if all args are BaseConfigSchema subclasses
                if (
                    cls._all_base_config_schemas(non_none_args)
                    and not field_info.discriminator
                ):
                    raise ValueError(
                        f"Union field '{field_name}' with BaseConfigSchema types "
                        f"must have a discriminator field specified."
                    )

        return values

    @staticmethod
    def _all_base_config_schemas(types_list) -> bool:
        """Check if all types in the list are BaseConfigSchema subclasses."""
        return all(
            hasattr(arg, "__bases__") and issubclass(arg, BaseConfigSchema)
            for arg in types_list
        )

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
