## 1. Validate saved templates and newly created servers

- [x] 1.1 Add focused game-target extraction and initialization-validation helpers. Cover the existing map/list environment and short/long port forms, TCP default/selection, fixed container target `25565`, explicit matching `SERVER_PORT`, and property-management flag validation without making legacy read parsers stricter.
- [x] 1.2 Add template-aware validation to template creation and updates before persistence. Keep host-port and unrelated placeholders without requiring defaults; reject placeholders/unresolved values in the critical game target, environment port, and explicit property-management flags.
- [x] 1.3 Validate final direct or rendered template YAML in `create_server_full()` before creating resources. Keep existing-server render/edit/rebuild, adoption, lifecycle, and snapshot paths outside the new initialization rule, and return actionable Chinese errors through the existing API error handling.
- [x] 1.4 Add targeted helper, template-save, and server-creation tests for valid alternate host ports, invalid/missing ports, UDP-only mappings, disabled property management, placeholder behavior, and rejection before side effects. Update affected creation fixtures while retaining explicit legacy fixtures without `SERVER_PORT`.
- [x] 1.5 Add or extend regression coverage showing that legacy servers remain readable, participate in port-conflict checks, and retain existing snapshot-edit/rebuild/lifecycle behavior without adding `SERVER_PORT`.

## 2. Add the game-port consistency self-check

- [x] 2.1 Register `server.game_port_consistency` in the server check category, catalog IDs/labels, and enabled-by-default dynamic-config toggle, preserving defaults when loading older self-check settings.
- [x] 2.2 Implement asynchronous per-server file-to-container-target comparison over active records, including stopped servers. Skip recognized startup and missing files on non-running servers; report mismatches as warnings and isolate unreadable/invalid inputs as server-specific warning-severity failed findings. Do not inspect Compose environment values or deployed container settings.
- [x] 2.3 Include narrow port/path/error evidence and static Chinese remediation for file editing, restart, and the conditional Compose override/recreate case. Preserve existing result schemas, history, check controls, and triggers without adding writes or background startup waits.
- [x] 2.4 Add self-check tests for legacy matching files, mismatches, ignored environment differences, missing/invalid values, starting and stopped states, per-server error isolation, enabled defaults, disabled-current-state projection, retained evidence, and correction followed by a single-check rerun.

## 3. Link findings to the existing file editor workflow

- [x] 3.1 Add a remediation-area link for this check's server-associated mismatch/file failures, deriving an encoded local file-browser URL with `path=/`, `q=server.properties`, and `regex=false` from the existing finding data. Reuse the current/history finding renderer and existing URL search behavior without new API fields, Markdown parsing, or automatic editing.
- [x] 3.2 Add Chinese labels for the new evidence and link, and update contextual template/create/Compose help with safe initialization examples. Keep the shared editor schema permissive for legacy YAML that omits `SERVER_PORT`, and retain the file editor's existing override reminder.
- [x] 3.3 Verify navigation from current and retained findings, correct server/data-root selection, populated literal search, reload/back navigation, normal file opening, and existing authentication handling using the current browser workflow.

## 4. Documentation and final verification

- [x] 4.1 Update the current-state Minecraft, template, self-check, and frontend file/self-check design docs, plus relevant scoped CLAUDE.md descriptions. Document scoped input compatibility, no bulk migration, skipped-state behavior, and the link/restart guidance without implying a runtime connectivity guarantee.
- [x] 4.2 Run the affected backend tests in `tests/templates/`, `tests/servers/`, `tests/self_check/`, `tests/test_create_server.py`, `tests/test_compose.py`, and `tests/test_compose_file.py` with appropriate Docker/integration exclusions, plus any other directly affected test module. Run `uv run pyright` and available IDE diagnostics; record a diagnostics-tool limitation if none is available.
- [x] 4.3 Run frontend `pnpm lint` and `pnpm build`, then verify the completed diff stays within the two planned work items and contains no database migration, template/server bulk rewrite, lifecycle gate, or new event trigger.
