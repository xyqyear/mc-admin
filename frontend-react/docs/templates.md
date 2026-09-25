# Server Templates (Frontend)

UI for managing reusable Docker Compose templates with typed variables, plus the bidirectional template ↔ direct-mode conversion flow on existing servers. Three pages and one multi-step wizard modal carry most of the surface area.

## Pages

- `features/templates/TemplateListScreen.tsx` — list at `/templates`. Table shows name, description, variable count, timestamps. Per-row actions: copy, edit, delete (confirmed via `useConfirm`).
- `features/templates/TemplateEditScreen.tsx` — `/templates/new`, `/templates/{id}/edit`, or `/templates/new?copyFrom={id}` (URL param drives create / edit / copy-from mode).
- `features/templates/DefaultVariablesScreen.tsx` — `/templates/default-variables`. Single-form editor for the default variable set that pre-fills new templates.

## `TemplateEdit` — three-tab editor

Template names, descriptions, YAML, variable definitions and default-variable lists use resource-scoped local drafts. Comparisons fetch a current server baseline without replacing authored fields. Failed saves retain the form; failed initial reads show a retry action. Server Compose and template-parameter forms additionally use versioned baseline/draft/remote sessions in `features/configuration`; confirmed reload replaces edits only after the read succeeds. See `data-architecture.md` for the shared draft lifecycle.

The most complex frontend page. Left panel: name + description inputs. Right panel: tabs.

1. **YAML editor** — Monaco with the docker-minecraft-server compose schema attached. Variable placeholders `{var}` are written inline; the editor doesn't try to highlight them specially.
2. **Variable definitions** — `VariableDefinitionForm.tsx` renders a sortable table of `VariableDefinition`s. Each row's edit button opens `VariableEditDialog.tsx` (modal): type picker, type-specific constraint fields (min/max for numerics, pattern for strings, options for enum), default value.
3. **Diff preview** — Monaco diff editor comparing the *current* working YAML against the *last saved* YAML. Useful before save to see what's changing.

### Validation

`extractVariablesFromYaml` walks the YAML for `{name}` placeholders. Cross-checks against the variable definitions array:

- Placeholder used but not defined → error
- Variable defined but not used → error (strict; blocks save)
- Duplicate variable name → error

The save button is disabled while any of these is non-empty. The backend save boundary also validates regular-expression syntax, numeric bound ordering, and defaults against their own constraints; rejected saves leave the existing template/default definitions unchanged.

## Mode conversion

`features/configuration/components/ConvertModeDialog.tsx` is a multi-step wizard. Three flows share it:

- **Template → Direct**: one-step confirmation. The server's `template_id` is cleared, the rendered YAML becomes the new direct compose. No rebuild needed.
- **Direct → Template**: 3 steps —
  1. **Pick a template** from the available templates
  2. **Extract / adjust variables** — calls POST `/servers/{id}/extract-variables` with the target template ID. The hook returns inferred values + warnings (placeholders that didn't match cleanly). The user edits the form to fix anything weird.
  3. **Preview diff and confirm** — Monaco diff between the current compose and the rendered-from-template YAML. If they match semantically (POST `/servers/{id}/check-conversion`), conversion is metadata-only. Otherwise a `SERVER_REBUILD` background task runs and `RebuildProgressDialog` watches it.
- **Template update**: same shape as direct → template, but starts from the server's existing template binding. Used when the bound template was edited and the user wants to apply the changes.

Existing-server variable diff previews use `POST /servers/{id}/template-config/preview`, which renders the stored server snapshot just like submitting a variable update. The live-template preview remains used by creation and explicit upgrade/conversion flows. An edited or deleted source template does not redirect ordinary server edits.

All configuration writes and mode conversions send the accepted `expected_version`. Preview/extraction/check responses do not silently replace that accepted version. A conflict retains YAML or variable drafts, shows the original baseline against current remote content plus the intended draft, and requires explicit acceptance before resubmitting. Mode-conversion variables remain intact and the preview/check runs again after acceptance.

Rebuild submission announces task/operation discovery. The authenticated app's operation observer owns business-cache refresh through the feature resource registry after terminal outcomes, including failures with partial changes, regardless of the current page. `RebuildProgressDialog` reports task progress, completion and failure; async `configuration_conflict` failures reopen conflict resolution without losing the draft.

## Default variables

`features/templates/DefaultVariablesScreen.tsx` edits a singleton `DefaultVariableConfig` row. Built-in defaults (loaded server-side):

- `name` — string, regex `^[a-z0-9-_]+$`, 1–20 chars
- `java_version` — enum
- `game_version` — string
- `max_memory` — int, 1–16 GB, default 6
- `game_port` / `rcon_port` — int, 1024–65535

Saving updates the singleton; subsequent template creations use the new defaults.

## Files

- `features/templates/TemplateListScreen.tsx`, `TemplateEdit.tsx`, `DefaultVariables.tsx`
- `features/templates/ui/VariableDefinitionForm.tsx`, `VariableEditDialog.tsx`, `SortableVariableRow.tsx`, `variableUtils.ts`
- `features/configuration/components/ConvertModeDialog.tsx`, `features/configuration/components/RebuildProgressDialog.tsx`
- `shared/editors/compose/ComposeDiffDialog.tsx`
- `features/servers/ui/ServerNew/TemplateCreationMode.tsx`, `TraditionalCreationMode.tsx`
- `features/configuration/ConfigurationScreen.tsx`, `components/TemplateMode.tsx`, `components/DirectMode.tsx`
- `features/configuration/contracts.ts`, `api.ts`, `queries.ts`, `commands.ts`, `useConfigurationSession.ts`, `operationResources.ts`
- `features/templates/api.ts`, `features/templates/queries.ts`, `features/templates/commands.ts`
