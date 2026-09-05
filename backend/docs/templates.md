# Server Templates (`app.templates`)

Reusable Docker Compose configurations with typed variable placeholders. A template is the YAML you'd hand-author for a server with `{name}`, `{max_memory}`, `{game_port}`, … left as variables, paired with typed `VariableDefinition`s. Creating a server from the template renders the YAML and stores both the rendered compose and the template snapshot used to render it.

## Why snapshots

A server bound to a template stays editable through the variable form forever — but the template itself can be edited, copied, deleted. If a server pointed at a *live* template id, deleting that template would orphan the server. Instead, `Server.template_snapshot_json` stores the immutable `TemplateSnapshot` (yaml + variable definitions) the server was created with. Server operations don't depend on the live template existing; the live template is only consulted when the user opts into a template-update.

## `VariableDefinition` discriminated union

Five types, all sharing `name`, `display_name`, `description`, `default`:

| Type     | Extra fields                                  |
| -------- | --------------------------------------------- |
| `int`    | `min_value`, `max_value`                      |
| `float`  | `min_value`, `max_value`                      |
| `string` | `max_length`, `pattern` (regex)               |
| `enum`   | `options: list[str]` (default validated ∈)    |
| `bool`   | —                                             |

Template saves validate placeholder definitions and fixed game-port initialization. Rendering validates supplied variable values; new-server creation also validates the final rendered initialization configuration before creating resources.

## `TemplateManager`

Pure functions, no state:

- `extract_variables_from_yaml(yaml)` → `set[str]` — finds every `{name}` placeholder.
- `validate_template(yaml, variables)` → `list[str]` errors. Every YAML placeholder must have a definition, every definition must appear in the YAML, and names cannot repeat. Once those checks pass, validate game-port initialization through `app.minecraft.game_port`.
- `render_yaml(yaml, values)` → `str`. Substitutes `{var}`; raises on missing.
- `generate_json_schema(variables)` → dict. rjsf-compatible JSON Schema; the frontend's `SchemaForm` renders the variable form from this.
- `validate_variable_values(variables, values)` → `list[str]` errors.
- `get_default_values(variables)` → `dict`.
- `extract_variables_from_compose(yaml_template, compose_yaml, variables)` → `(values, warnings)`. Reverse-extraction: line-by-line regex match against the template to infer what a hand-edited compose's variable values would be. Used by the direct-→-template mode conversion.

## Two server modes

Reusable template creation and partial updates validate the effective YAML before persistence. Templates must contain literal `SERVER_PORT=25565` and a TCP container target of `25565`. Explicit `OVERRIDE_SERVER_PROPERTIES` must be true and explicit `SKIP_SERVER_PROPERTIES` must be false; both may be omitted. Critical fields cannot be supplied only by placeholders, Compose interpolation, or `env_file`. Host-port and unrelated placeholders remain supported without requiring defaults. Scalar markers allow parsing their structure without rendering a sample configuration.

An older reusable template must be corrected before it can be saved or used to create a new server. Existing servers continue using their immutable snapshots for reads, edits, and rebuilds without adding `SERVER_PORT`. The shared renderer does not enforce initialization policy, and no stored template or server is rewritten automatically.

A server is in **template mode** if `Server.template_id` is set; otherwise **direct mode**.

- **Template mode**: variable values live in `Server.variable_values_json`. Editing the variable form re-renders the YAML; if the rendered output differs semantically from the stored compose, a `SERVER_REBUILD` background task is submitted (the compose is replaced and `docker compose up -d` runs). DB row updated only after rebuild succeeds.
- **Direct mode**: the YAML in `Server.compose_file` is authoritative. No template association.

Conversions both directions live in `routers/servers/template_migration.py`. Direct → template uses `extract_variables_from_compose`; if the rendered YAML matches semantically (`are_yaml_semantically_equal()` ignores formatting), the conversion is metadata-only — no rebuild.

## Default variables

`DefaultVariableConfig` is a single-row table holding the variable set that pre-populates new templates. Lets an admin standardize "every template here uses `{game_port}` with these constraints". Built-in defaults: `name` (regex `^[a-z0-9-_]+$`), `java_version` (enum), `game_version`, `max_memory` (1–16 GB), `game_port` / `rcon_port` (1024–65535).

## Files

- `models.py` — `VariableDefinition` discriminated union, `TemplateSnapshot`, request/response models
- `manager.py` — `TemplateManager` (pure-function class)
- `crud.py` — `ServerTemplate` CRUD
- `default_variables_crud.py` — `DefaultVariableConfig` singleton CRUD
- `yaml_utils.py` — `are_yaml_semantically_equal()`
