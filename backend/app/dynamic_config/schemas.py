"""
Dynamic configuration schemas with support for nested models and deprecated fields.
"""

import hashlib
import json
import types
from typing import Annotated, Any, Dict, Union, get_args, get_origin

from pydantic import BaseModel, model_validator
from pydantic.fields import FieldInfo
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

    @classmethod
    def get_json_schema(cls) -> Dict[str, Any]:
        """
        Generate a JSON Schema representation of this configuration schema.

        Returns:
            A dictionary representing the JSON Schema
        """
        definitions = {}

        def _get_type_schema(
            annotation: Any, definitions: Dict[str, Any], field_info: Any = None
        ) -> Dict[str, Any]:
            """Convert a Python type annotation to JSON Schema format."""
            origin = get_origin(annotation)
            args = get_args(annotation)

            # Handle Annotated types
            if origin is Annotated:
                actual_type = annotation.__args__[0]
                # Extract FieldInfo from metadata
                nested_field_info = next(
                    (
                        item
                        for item in annotation.__metadata__
                        if isinstance(item, FieldInfo)
                    ),
                    None,
                )
                use_field_info = nested_field_info or field_info
                return _get_type_schema(actual_type, definitions, use_field_info)

            # Handle Union types
            if origin in (Union, types.UnionType):
                non_none_args = [arg for arg in args if arg is not type(None)]

                # Optional field (Union[Type, None])
                if len(non_none_args) == 1:
                    return _get_type_schema(non_none_args[0], definitions)

                # Multiple types - use oneOf
                one_of_schema: dict[str, Any] = {
                    "oneOf": [
                        _get_type_schema(arg, definitions, field_info)
                        for arg in non_none_args
                    ]
                }

                # Add discriminator if all are BaseConfigSchema and field_info has discriminator
                if (
                    cls._all_base_config_schemas(non_none_args)
                    and field_info
                    and field_info.discriminator
                ):
                    one_of_schema["discriminator"] = {
                        "propertyName": field_info.discriminator
                    }

                return one_of_schema

            # Handle specific container types
            if origin is list:
                return (
                    {
                        "type": "array",
                        "items": _get_type_schema(args[0], definitions, field_info),
                    }
                    if args
                    else {"type": "array"}
                )

            if origin is dict:
                return {"type": "object"}

            # Handle Literal types
            if (
                hasattr(annotation, "__origin__")
                and str(annotation.__origin__) == "typing.Literal"
            ):
                return {
                    "type": "string" if isinstance(args[0], str) else "number",
                    "enum": list(args),
                }

            # Handle BaseConfigSchema subclasses
            if hasattr(annotation, "__bases__") and issubclass(
                annotation, BaseConfigSchema
            ):
                class_name = annotation.__name__
                if class_name not in definitions:
                    definitions[class_name] = _get_schema_dict_for_class(
                        annotation, definitions
                    )
                return {"$ref": f"#/definitions/{class_name}"}

            # Handle basic Python types
            type_mapping = {
                str: "string",
                int: "integer",
                float: "number",
                bool: "boolean",
                list: "array",
                dict: "object",
            }

            return {"type": type_mapping.get(annotation, "object")}

        def _get_schema_dict_for_class(
            schema_cls: type[BaseConfigSchema], definitions: Dict[str, Any]
        ) -> Dict[str, Any]:
            """Generate schema dictionary for a BaseConfigSchema class."""
            properties = {}
            required = []

            for field_name, field_info in schema_cls.model_fields.items():
                field_schema = _get_type_schema(
                    field_info.annotation, definitions, field_info
                )

                # Add description if available
                if field_info.description:
                    field_schema["description"] = field_info.description

                # Add default value if available (skip for oneOf fields as they're complex)
                if (
                    "oneOf" not in field_schema
                    and field_info.default is not PydanticUndefined
                ):
                    try:
                        if isinstance(field_info.default, BaseModel):
                            field_schema["default"] = json.loads(
                                field_info.default.model_dump_json()
                            )
                        else:
                            json.dumps(
                                field_info.default
                            )  # Validate JSON serialization
                            field_schema["default"] = field_info.default
                    except (TypeError, ValueError, AttributeError):
                        pass  # Skip non-serializable defaults

                properties[field_name] = field_schema

                if field_info.is_required():
                    required.append(field_name)

            schema_dict = {
                "type": "object",
                "title": schema_cls.__name__,
                "properties": properties,
            }

            if required:
                schema_dict["required"] = required

            return schema_dict

        # Generate the main schema
        main_schema = _get_schema_dict_for_class(cls, definitions)

        # Create the complete JSON Schema
        json_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": cls.__name__,
            **main_schema,
        }

        # Add definitions if any nested schemas were found
        if definitions:
            json_schema["definitions"] = definitions

        return json_schema
