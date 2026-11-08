## Why

Configuration modules and application pages ship together, but the current form generation layer obscures their data contracts and limits editing controls. Template variables already carry the complete domain definition needed to render their inputs directly.

## What Changes

- Render template values and variable definitions with ordinary business components.
- **BREAKING** Replace generic configuration discovery and writes with explicitly typed settings resources and dedicated sidebar pages.
- **BREAKING** Remove derived template form descriptions and scheduled-job parameter descriptions from API responses; declare job parameter contracts explicitly.
- Preserve stored settings, template snapshots, runtime update notifications, authored drafts and configuration conflict handling.
- Remove the form-engine dependencies and update the API scenarios, frontend behavior tests and current documentation.
- Non-goals: change database layout, alter Compose editor language assistance, redesign task execution or add configuration concurrency control.

## Capabilities

### New Capabilities

- `application-settings`: Authenticated, typed settings resources, dedicated navigation, complete editing and durable runtime updates.
- `template-variable-editing`: Definition-driven template inputs, type-specific variable authoring and snapshot-preserving server editing.

### Modified Capabilities

- `administration-compatibility`: Preserve authored values when template definitions or suggested ports refresh.

## Impact

Backend settings/template/cron HTTP contracts, frontend settings/templates/configuration/servers/schedules/navigation, related API E2E and browser coverage, dependencies and component documentation. Existing persisted module keys and JSON values remain valid. Application image construction is unchanged apart from the smaller frontend dependency graph.
