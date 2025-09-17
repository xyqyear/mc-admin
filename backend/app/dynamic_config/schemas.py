"""
Dynamic configuration schemas with support for nested models and deprecated fields.
"""

import hashlib
import json
import types
from typing import Any, Dict, Union, get_args, get_origin

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
        # This validator runs on class definition, not instance creation
        # We validate the schema structure itself
        for field_name, field_info in cls.model_fields.items():
            annotation = field_info.annotation
            origin = get_origin(annotation)

            # Check if this field is a Union or types.UnionType
            if origin is Union or origin is types.UnionType:
                args = get_args(annotation)
                # Filter out NoneType for optional fields
                non_none_args = [arg for arg in args if arg is not type(None)]

                # Skip if this is just an optional field (Union[Type, None])
                if len(non_none_args) <= 1:
                    continue

                # Check if all non-None args are BaseConfigSchema subclasses
                are_all_base_config = all(
                    hasattr(arg, "__bases__")
                    and arg is not None
                    and issubclass(arg, BaseConfigSchema)
                    for arg in non_none_args
                )

                are_none_base_config = all(
                    not (
                        hasattr(arg, "__bases__")
                        and arg is not None
                        and issubclass(arg, BaseConfigSchema)
                    )
                    for arg in non_none_args
                )

                # Enforce the rule: either all or none must be BaseConfigSchema
                if not (are_all_base_config or are_none_base_config):
                    raise ValueError(
                        f"Field '{field_name}' has a Union with mixed BaseConfigSchema and non-BaseConfigSchema types. "
                        f"All Union members must be BaseConfigSchema subclasses or none of them should be."
                    )

                # If all are BaseConfigSchema, ensure each has a 'type' field with Literal type
                if are_all_base_config:
                    for arg in non_none_args:
                        if "type" not in arg.model_fields:
                            raise ValueError(
                                f"BaseConfigSchema subclass '{arg.__name__}' in Union field '{field_name}' "
                                f"must have a 'type' field for discrimination."
                            )

                        type_field = arg.model_fields["type"]
                        type_annotation = type_field.annotation

                        # Check if it's a Literal type
                        if not (
                            hasattr(type_annotation, "__origin__")
                            and str(type_annotation.__origin__) == "typing.Literal"
                        ):
                            raise ValueError(
                                f"BaseConfigSchema subclass '{arg.__name__}' in Union field '{field_name}' "
                                f"must have a 'type' field with Literal[] annotation for discrimination."
                            )

        return values

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
            elif field_info.default_factory is not None:
                default_str = str(field_info.default_factory())  # type: ignore

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
            annotation: Any, definitions: Dict[str, Any]
        ) -> Dict[str, Any]:
            """Convert a Python type annotation to JSON Schema format."""
            origin = get_origin(annotation)
            args = get_args(annotation)

            # Handle Union types (TypeA | TypeB or Union[TypeA, TypeB])
            if origin is Union or origin is types.UnionType:
                # Filter out NoneType for optional fields
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    # Optional field (Union[Type, None])
                    return _get_type_schema(non_none_args[0], definitions)
                else:
                    # Multiple types - use oneOf
                    one_of_schema: Dict[str, Any] = {
                        "oneOf": [
                            _get_type_schema(arg, definitions) for arg in non_none_args
                        ]
                    }

                    # Check if all non-None args are BaseConfigSchema subclasses
                    are_all_base_config = all(
                        hasattr(arg, "__bases__")
                        and arg is not None
                        and issubclass(arg, BaseConfigSchema)
                        for arg in non_none_args
                    )

                    # Add discriminator if all are BaseConfigSchema
                    if are_all_base_config:
                        one_of_schema["discriminator"] = {"propertyName": "type"}

                    return one_of_schema

            # Handle List types
            if origin is list:
                if args:
                    item_schema = _get_type_schema(args[0], definitions)
                    return {"type": "array", "items": item_schema}
                else:
                    return {"type": "array"}

            # Handle Dict types
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
            if (
                hasattr(annotation, "__bases__")
                and annotation is not None
                and issubclass(annotation, BaseConfigSchema)
            ):
                # Add to definitions if not already present
                class_name = annotation.__name__
                if class_name not in definitions:
                    definitions[class_name] = _get_schema_dict_for_class(
                        annotation, definitions
                    )
                return {"$ref": f"#/definitions/{class_name}"}

            # Handle basic Python types
            if annotation is str:
                return {"type": "string"}
            elif annotation is int:
                return {"type": "integer"}
            elif annotation is float:
                return {"type": "number"}
            elif annotation is bool:
                return {"type": "boolean"}
            elif annotation is list:
                return {"type": "array"}
            elif annotation is dict:
                return {"type": "object"}
            else:
                # Fallback to generic object
                return {"type": "object"}

        def _get_schema_dict_for_class(
            schema_cls: type[BaseConfigSchema], definitions: Dict[str, Any]
        ) -> Dict[str, Any]:
            """Generate schema dictionary for a BaseConfigSchema class."""
            properties = {}
            required = []

            for field_name, field_info in schema_cls.model_fields.items():
                field_schema = _get_type_schema(field_info.annotation, definitions)

                # Add description if available
                if field_info.description:
                    field_schema["description"] = field_info.description

                # Step 1: Check if this field uses oneOf
                is_one_of_field = "oneOf" in field_schema

                # Step 2: Get default value (skip for oneOf fields)
                default_value = None
                has_default = False

                if not is_one_of_field:  # Only process defaults for non-oneOf fields
                    if field_info.default is not PydanticUndefined:
                        default_value = field_info.default
                        has_default = True
                    elif (
                        hasattr(field_info, "default_factory")
                        and field_info.default_factory is not None
                    ):
                        try:
                            default_value = field_info.default_factory()  # type: ignore
                            has_default = True
                        except Exception:
                            # If factory fails, skip default
                            has_default = False

                # Step 3: Process default value to JSON (skip for oneOf fields)
                if has_default and not is_one_of_field:
                    try:
                        # Check if default_value is a BaseModel instance
                        if isinstance(default_value, BaseModel):
                            field_schema["default"] = json.loads(
                                default_value.model_dump_json()
                            )
                        else:
                            # Try to serialize with json.dumps
                            json.dumps(default_value)
                            field_schema["default"] = default_value
                    except (TypeError, ValueError, AttributeError):
                        # If JSON serialization fails, skip default
                        pass

                properties[field_name] = field_schema

                # Add to required if field is required
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
