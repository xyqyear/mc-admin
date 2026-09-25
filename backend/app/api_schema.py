from typing import Any

from fastapi import FastAPI

PUBLIC_SCHEMA_NAMES = {
    "app__servers__api_models__ServerInfo": "app__routers__servers__misc__ServerInfo",
    "app__self_check__system_models__ServerInfo": "app__routers__system__ServerInfo",
    "app__world__api_models__RestoreRequest": "app__routers__servers__world_restore__RestoreRequest",
    "app__snapshots__api_models__RestoreRequest": "app__routers__snapshots__RestoreRequest",
}


def preserve_public_schema_names(app: FastAPI) -> None:
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        schema = generate()
        definitions = schema.get("components", {}).get("schemas", {})
        references = {}
        for internal, public in PUBLIC_SCHEMA_NAMES.items():
            if internal not in definitions:
                continue
            if public in definitions:
                raise RuntimeError(f"Duplicate public schema name: {public}")
            definitions[public] = definitions.pop(internal)
            references[f"#/components/schemas/{internal}"] = f"#/components/schemas/{public}"

        def replace(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "$ref" and isinstance(child, str) and child in references:
                        value[key] = references[child]
                    else:
                        replace(child)
            elif isinstance(value, list):
                for child in value:
                    replace(child)

        if references:
            replace(schema)
        return schema

    app.openapi = openapi
