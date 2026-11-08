## Context

See proposal.md for intent. Configuration lifecycle and draft invariants are owned by backend/docs/dynamic-config.md and frontend-react/docs/configuration.md. The application has fixed settings modules and ships API and frontend together.

## Goals / Non-Goals

Use explicit resource contracts and business controls. Keep persisted module keys, current values, template snapshots, operation observation and conflict handling. Leave database layout, task execution and Compose language services unchanged.

## Decisions

- Declare GET/PUT/POST-reset routes per `/settings/<resource>` with concrete Pydantic types. Return effective data directly. Keep configuration loading, migration, validation and notifications in ConfigManager; remove description discovery. Persist normalized validated values.
- Implement dedicated settings screens under the settings feature with typed transport and query contracts. Share editing chrome and primitive controls, not field descriptions. Use textarea for parser rules, Monaco for the player command and explicit list/map editors. Keep resource-scoped drafts and confirmation of reload/reset.
- Add an expanded settings sidebar group and explicit `/settings/*` routes. Keep DNS operational management separate from DNS settings. DNS save retains its synchronization outcome handling in the DNS-specific command.
- Render template values from the existing VariableDefinition union. Use snapshot definitions on existing servers and template detail on creation. Variable authoring uses ordinary controlled inputs with type-specific validation.
- Give scheduled-job writes an identifier-discriminated parameter contract. Keep registration metadata required for availability/system schedules. Use explicit backup/restart controls, preserving null/empty semantics and explicit-save behavior.
- Remove unused wrappers, derived form fields/endpoints, runtime description generation and the four form-engine dependencies. Keep standard API documentation and editor language assistance.

## Risks / Trade-offs

- Contract drift → synchronize backend models, frontend contracts, controls and behavior coverage in one change; add a short cross-component maintenance instruction.
- Data loss during conversion → retain persisted keys and formats, preserve defaults and explicit values, test failed writes and legacy loading.
- Draft replacement during refresh → retain existing draft/session ownership and resource keys.
- Invalid parameter migration → retain server domain validation and independent API outcome assertions.

## Migration Plan

Deploy frontend and backend together. No database revision is required. Rollback uses the same stored data format. Update backend dynamic configuration/template/cron documentation, frontend settings/template/cron/navigation documentation and API coverage inventories. Validate selected affected tests, required static/build checks and latest-SHA qualification after commit/push.
