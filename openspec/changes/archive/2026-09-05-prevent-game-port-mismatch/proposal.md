## Why

An imported `server.properties` can configure a game port different from the container port published by Compose, preventing connections through that mapping. Existing servers intentionally omit `SERVER_PORT`, so prevention for new configurations must coexist with a small, file-based diagnostic that does not require migrating those servers.

## What Changes

- **BREAKING for template saves and new server creation:** require an explicit `SERVER_PORT` matching the supported game container target, currently `25565`, with a TCP game mapping. Reject explicit settings that disable property management (`OVERRIDE_SERVER_PROPERTIES=false` or `SKIP_SERVER_PROPERTIES=true`). Apply this to template creation/editing and final new-server YAML in both direct and template modes.
- Keep existing server reads, port discovery, configuration edits/rebuilds, template snapshots, adoption, and lifecycle operations compatible with Compose files that omit `SERVER_PORT`. Do not migrate stored configurations.
- Add the enabled-by-default `server.game_port_consistency` self-check. Compare `server.properties` against the Compose game container target for each active server, including stopped servers. Do not audit Compose environment variables or deployed container configuration in this check.
- Report uninitialized or starting servers without premature mismatch warnings, isolate unreadable/invalid configuration per server, and retain results through the existing self-check system.
- Add a remediation link that opens the affected server's data-root file browser with `server.properties` already entered as a literal filename search. Provide static guidance about restarting after file edits and rebuilding when a conflicting Compose environment variable would overwrite the file.
- Keep the scope to these two work items and their editor/help documentation. Non-goals: automatic repair, bulk template/server migration, new lifecycle gates or event triggers, Docker environment resolution/inspection, socket probes, arbitrary game container ports, RCON validation changes, and firewall/DNS/connectivity diagnosis.

## Capabilities

### New Capabilities

- `game-port-configuration`: Initialization-port validation for saved templates and newly created servers, with compatibility for existing server configurations.
- `game-port-self-check`: File-to-Compose game-port comparison, lifecycle-aware findings, and navigation to the file that needs editing.

### Modified Capabilities

None.

## Impact

- Backend: template save validation, bundled server creation, shared Minecraft configuration helpers, and the self-check catalog/configuration/check implementation.
- Frontend: self-check remediation rendering, existing file-browser navigation, and contextual Compose/template help. No new file editor or search flow is needed.
- APIs: existing template save and server creation endpoints reject unsafe new submissions with actionable validation errors. Self-check endpoints expose one additional catalog ID and its findings using the existing response shape. Authentication and authorization remain unchanged.
- Persistence: reuse retained findings, evidence, remediation text, and dynamic configuration defaults. No database migration or rewrite of templates, snapshots, Compose files, or server properties.
- Docker: no new execution or inspection commands. The image continues to apply explicit initialization variables on startup; ordinary restart/rebuild behavior is unchanged.
- Documentation and verification: update the relevant current-state design docs and CLAUDE.md references during implementation, add targeted backend regression coverage, verify the existing file-link navigation, and run the required static checks.
