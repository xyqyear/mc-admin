# Server Templates (Frontend)

UI for managing reusable Docker Compose templates with typed variables, plus the bidirectional template ↔ direct-mode conversion flow on existing servers. Three pages and one multi-step wizard modal carry most of the surface area.

## Pages

- `pages/templates/TemplateList.tsx` — list at `/templates`. Table shows name, description, variable count, timestamps. Per-row actions: copy, edit, delete (confirmed via `useConfirm`).
- `pages/templates/TemplateEdit.tsx` — `/templates/new`, `/templates/{id}/edit`, or `/templates/new?copyFrom={id}` (URL param drives create / edit / copy-from mode).
- `pages/templates/DefaultVariables.tsx` — `/templates/defaults`. Single-form editor for the default variable set that pre-fills new templates.

## `TemplateEdit` — three-tab editor

The most complex frontend page. Left panel: name + description inputs. Right panel: tabs.

1. **YAML editor** — Monaco with the docker-minecraft-server compose schema attached. Variable placeholders `{var}` are written inline; the editor doesn't try to highlight them specially.
2. **Variable definitions** — `VariableDefinitionForm.tsx` renders a sortable table of `VariableDefinition`s. Each row's edit button opens `VariableEditDialog.tsx` (modal): type picker, type-specific constraint fields (min/max for numerics, pattern for strings, options for enum), default value.
3. **Diff preview** — Monaco diff editor comparing the *current* working YAML against the *last saved* YAML. Useful before save to see what's changing.

### Validation

`extractVariablesFromYaml` walks the YAML for `{name}` placeholders. Cross-checks against the variable definitions array:

- Placeholder used but not defined → error
- Variable defined but not used → error (strict; blocks save)
- Duplicate variable name → error

The save button is disabled while any of these is non-empty.

## Mode conversion

`components/modals/ConvertModeModal.tsx` is a multi-step wizard. Three flows share it:

- **Template → Direct**: one-step confirmation. The server's `template_id` is cleared, the rendered YAML becomes the new direct compose. No rebuild needed.
- **Direct → Template**: 3 steps —
  1. **Pick a template** (filtered to ones whose render output could plausibly match)
  2. **Extract / adjust variables** — calls `useExtractVariables` (POST `/templates/{id}/extract-variables` with the current compose). The hook returns inferred values + warnings (placeholders that didn't match cleanly). The user edits the form to fix anything weird.
  3. **Preview diff and confirm** — Monaco diff between the current compose and the rendered-from-template YAML. If they match semantically (`useCheckConversion`), conversion is metadata-only. Otherwise a `SERVER_REBUILD` background task runs and `RebuildProgressModal` watches it.
- **Template update**: same shape as direct → template, but starts from the server's existing template binding. Used when the bound template was edited and the user wants to apply the changes.

## Default variables

`pages/templates/DefaultVariables.tsx` edits a singleton `DefaultVariableConfig` row. Built-in defaults (loaded server-side):

- `name` — string, regex `^[a-z0-9-_]+$`, 1–20 chars
- `java_version` — enum
- `game_version` — string
- `max_memory` — int, 1–16 GB, default 6
- `game_port` / `rcon_port` — int, 1024–65535

Saving updates the singleton; subsequent template creations use the new defaults.

## Files

- `pages/templates/TemplateList.tsx`, `TemplateEdit.tsx`, `DefaultVariables.tsx`
- `components/templates/VariableDefinitionForm.tsx`, `VariableEditDialog.tsx`, `SortableVariableRow.tsx`, `variableUtils.ts`
- `components/modals/ConvertModeModal.tsx`, `RebuildProgressModal.tsx`
- `components/modals/ServerCompose/ComposeDiffModal.tsx`
- `components/server/ServerNew/TemplateCreationMode.tsx`, `TraditionalCreationMode.tsx`
- `components/server/ServerCompose/TemplateMode.tsx`, `DirectMode.tsx`
- `hooks/api/templateApi.ts`, `hooks/queries/base/useTemplateQueries.ts`, `hooks/mutations/useTemplateMutations.ts`
