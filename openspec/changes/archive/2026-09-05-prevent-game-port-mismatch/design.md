## Context

See [proposal.md](proposal.md) for motivation and scope. This design spans template/server input validation, self-check execution, and frontend remediation, so a design artifact is warranted even though the feature introduces no dependency or database migration.

Current integration points:

- [Minecraft management](../../../backend/docs/minecraft.md): `MCComposeFile` identifies the game mapping by target `25565`. `get_game_port()` returns its published host port, so it is not the comparison value for the diagnostic. The constructor is also used on read paths and during port-conflict scanning.
- [Templates](../../../backend/docs/templates.md): `TemplateManager.validate_template()` checks variable-definition consistency, not Minecraft configuration. Template save endpoints validate the effective stored/submitted template before writing. `create_server_full()` is the common boundary for new direct and template-based servers. Existing servers retain immutable template snapshots.
- [Self-check](../../../backend/docs/self-check.md): catalog definitions, per-check configuration toggles, result persistence, single-check reruns, existing event triggers, and failure isolation already exist. `SelfCheckContext.active_servers()` includes stopped active records. A new check must be added coherently to constants, labels, definitions, and configuration mappings.
- [Dashboard](../../../frontend-react/docs/self-check.md): `SelfCheck.tsx` renders remediation as plain text, with evidence and server IDs available in each finding. History and current-state views share the finding renderer.
- [File management](../../../frontend-react/docs/file-management.md): `ServerFiles.tsx` already reads `path`, `q`, and `regex` from the URL and synchronizes both displayed search results and search input. The file editor already displays a Compose-override reminder for `server.properties`.

## Goals / Non-Goals

**Goals:**

- Use small shared port helpers while keeping strict initialization validation separate from permissive legacy reads.
- Implement the two behavior contracts in [game-port-configuration](specs/game-port-configuration/spec.md) and [game-port-self-check](specs/game-port-self-check/spec.md) through existing extension points.
- Keep all diagnostics read-only and avoid automatic edits, server interruption, or persistence schema changes.

**Non-Goals:**

- A general Compose evaluator or validation-mode framework.
- Validation of every edit/rebuild of an existing server, scanning reusable templates in self-check, or updating template snapshots.
- Inspecting deployed container settings, predicting every image override mechanism, checking actual sockets, or adding startup gates and event scheduling.

## Decisions

### 1. Separate initialization validation from game-target extraction

Add a focused module such as `app/minecraft/game_port.py` containing a small target extractor and an initialization validator. The extractor only needs the Minecraft service's supported TCP game mapping; it does not require `SERVER_PORT` or inspect other environment settings. It returns the container target and optionally the published mapping for evidence. It must not call `get_game_port()` and mistake the host port for the target.

The initialization validator additionally requires explicit `SERVER_PORT=25565`, checks equality with the supported target, and rejects property-management flags that disable startup updates. Normalize environment maps/lists and the existing short/long mapping forms. An omitted protocol is TCP. Reject Boolean or non-integral port input before permissive numeric coercion hides it. Accept native booleans and explicit case-insensitive `true`/`false` strings for the flags; reject unresolved or unrecognized forms with a field-specific error.

Only the supported game target remains fixed; host-port selection continues through the existing allocator and conflict checks. Do not require `SERVER_PORT` inside `MCComposeFile`, `MCInstance._verify_compose_yaml()`, or `extract_ports_from_yaml()`, since these paths also read legacy configurations. A globally stricter parser was considered and rejected because port-conflict scanning currently skips parse failures, which could conceal occupied ports after upgrading.

### 2. Validate templates without synthesizing variable defaults

Keep existing placeholder/definition checks in `TemplateManager.validate_template()`, then validate the critical Minecraft initialization fields with a template-aware adapter. Preserve ordinary placeholders in names, versions, memory, and published host ports. Protect placeholders as scalar markers when parsing template structure if needed, and inspect the literal container target rather than trying to convert a host placeholder into an integer.

Require literal `SERVER_PORT`, the supported game container target, and any explicit property-management flags. This is a deliberate constraint consistent with a fixed internal port. It avoids a symbolic validator or testing one sample rendering that does not guarantee all user values. Other template variables need no defaults just to save a template. Critical values supplied only through `env_file`, Compose interpolation, or template placeholders are not accepted at these new validation boundaries; the error asks for an explicit inline value.

Apply validation before persistence in template create/update, using the effective template for partial updates as the router already does. In `create_server_full()`, validate final YAML after resolving direct/template input and before creating files, records, cron jobs, or containers. This final check catches old reusable templates and any configuration changed between template preparation and server submission. It does not require new locks or change transaction semantics.

Do not route these new rules through the shared render function: existing server template-variable edits and rebuilds use that function and must remain compatible with snapshots lacking `SERVER_PORT`. Reusable template saves become stricter, including saves of an old template; existing server operations do not. This preserves the user's requested small scope instead of widening enforcement to migration, rebuild, or adoption paths.

### 3. Register one read-only, per-server diagnostic

Implement `check_game_port_consistency` in the existing server check category, registered as `server.game_port_consistency`. Add its label and enabled-by-default Boolean toggle in the existing self-check configuration. Use current active DB records rather than only running Docker containers.

For each server, use existing status access and asynchronous file access. Status reads are only to defer startup comparison; no container environment or port-binding inspection is added. Read the current Compose target with the read-only helper. Extract the final `server-port=value` assignment using the existing properties key/value convention, with an explicit presence/integer/range check, without validating unrelated fields. Missing or unusable values must not silently become `25565`. Keep per-server exceptions inside the loop.

Result policy:

| Condition | Severity / status | Interpretation |
| --- | --- | --- |
| No active server records | success / passed | Nothing to compare |
| Server reported as STARTING | info / skipped | Startup may still update the file |
| Non-running server has no properties file | info / skipped | File not yet available for comparison |
| Valid file port matches valid game target | success / passed | File and mapping agree |
| Valid file port differs from target | warning / warning | Report both values and file remediation |
| Invalid/unreadable Compose, invalid/unreadable properties, missing field, missing file while running, or unavailable status | warning / failed | Comparison could not be completed for this server |

Do not call an unbounded health-wait helper or introduce delayed background jobs. A starting server is rechecked by the next existing scheduled, manual, or event-triggered run. A stopped server with an imported mismatched file receives a warning even if a future startup might fix it: this diagnostic intentionally does not inspect environment variables to predict the next startup. A missing file on any non-running server is skipped because the current model does not reliably identify whether that server has ever generated properties.

Use evidence such as `expected_container_port`, `properties_server_port`, `properties_path`, `published_game_port`, and a narrow error description. Store one result per active server so mixed passed, skipped, warning, and failed outcomes are visible. Avoid dumping complete properties or Compose/environment data. Reuse existing run locking, history, enabled-check projection, and single-check rerun behavior; no persistence or API shape change is needed.

### 4. Build the remediation link in the existing finding renderer

For this check ID and a server-associated mismatch or properties-file failure, add a local navigation link in the remediation area. Derive the route from the existing `server_id`, encode the path segment, and build query parameters through `URLSearchParams`:

`/server/<encoded-server-id>/files?path=%2F&q=server.properties&regex=false`

The directory is `/` because this page exposes the server data directory, not the Compose project directory. The query is a literal search so the dot is not interpreted as a regex wildcard. `ServerFiles.tsx` already supports the link, including reload and back/forward search synchronization; avoid adding a second search state mechanism or automatically opening the editor.

Keep backend `remediation` as `list[str]` and preserve existing response/persistence schemas. The frontend can identify this one action from the stable check ID, server ID, status, and file-related evidence. Add concise localized labels for the new evidence keys. A generic backend action model or Markdown link parser was considered and rejected as unnecessary for one known internal destination. Current and retained findings use the same renderer, so the link works in both views. Existing authentication, authorization, missing-server, and file-edit conflict behavior remain authoritative.

Remediation text primarily directs the user to edit `server-port` to the expected target and restart after saving. Also include a conditional, static explanation: if Compose explicitly configures a conflicting `SERVER_PORT`, correct Compose and recreate the container using the existing workflow because a plain restart does not adopt environment changes. Do not suggest that an environment conflict was detected. Keep the current file editor's override reminder available.

### 5. Keep editor guidance compatible with legacy YAML

Add initialization hints and safe examples to the Compose help and relevant template/create UI. The shared Monaco schema can document `SERVER_PORT` and the property-management flags, but must not globally require them or mark legacy server editors invalid just because they omit the new initialization setting. Server-side validation remains authoritative at the scoped save/create boundaries.

During implementation, update `backend/docs/minecraft.md`, `backend/docs/templates.md`, `backend/docs/self-check.md`, `frontend-react/docs/self-check.md`, and the remediation-link description in `frontend-react/docs/file-management.md`. Update scoped CLAUDE.md orientation/contract descriptions only where the new helper or convention needs a day-to-day reference; keep detailed policy in those docs. Current-state documentation remains unchanged during this planning-only workflow.

## Risks / Trade-offs

- [Saved templates without `SERVER_PORT` cannot be saved or used for new creation until corrected] -> Mark this input-compatibility change in errors/help; existing server files and snapshots remain usable without a migration.
- [Literal critical template fields are less flexible] -> Internal game port is already fixed by the application; host port and unrelated variables retain their current flexibility.
- [A file can change between status and file reads, or while Java is running] -> Skip recognized startup, isolate parse failures, and label results as file/configuration consistency. No runtime-listener or future-startup guarantee is claimed.
- [A stopped imported file may be corrected by the image on the next startup] -> Report its present mismatch and retain the conditional override guidance instead of adding environment prediction.
- [The desired Compose file can differ from an existing container] -> Explicitly exclude deployed-configuration inspection; the remediation explains the recreate case without claiming it was checked.
- [Manual server edits can reintroduce a mismatch] -> Existing scheduled/manual checks remain the detection path; no new hard gate is added to legacy editing.
- [A historical finding can reference a removed server] -> Reuse normal file-page errors and authorization rather than making history links mutate or recreate resources.

## Migration Plan

1. Deploy the scoped input validator, check registration/default, and remediation renderer together. An older self-check config receives the new toggle through model defaults.
2. Update reusable templates through the ordinary template editor when they need to be saved or used for new creation. Do not run an automated update of templates, server snapshots, Compose files, or properties.
3. Run the existing full/manual self-check to inventory current file mismatches. Users repair individual files and rerun the item; restarting or rebuilding remains an explicit existing operation.
4. Rollback requires reverting application code only; no schema or stored-server rollback is required. The check can be disabled independently through its existing configuration surface, and existing retained findings remain readable.

## Validation Strategy

- Unit tests for supported input forms, target-versus-host comparison, TCP selection, missing/invalid ports, and property-management flags.
- Template API/manager tests for create/update rejection before persistence, placeholders without defaults in ordinary fields, and forbidden critical placeholders. Server creation tests cover both direct YAML and final rendered old-template output before resource creation.
- Regression tests keep missing-`SERVER_PORT` legacy reads, port-conflict participation, snapshot-based edits, and rebuild/lifecycle paths operational without passing the new validator.
- Self-check tests cover matching/mismatching files, ignored environment differences, stopped/startup/missing-file cases, per-server failures, enabled defaults, rerun projection, and retained evidence/remediation.
- Browser verification follows a current and retained finding to the data root, confirms the populated literal search, reloads the destination, and opens the existing editor. This uses the existing UI workflow and does not require a new frontend test framework.
- Run relevant backend test groups and `uv run pyright`; run frontend `pnpm lint` and `pnpm build`. Use available IDE diagnostics during implementation; if unavailable, record that limitation and use the required static checks. No Docker integration suite is needed for this read-only comparison and input-validation scope.

External behavior references: [itzg properties management](https://docker-minecraft-server.readthedocs.io/en/latest/configuration/server-properties/) and [Docker Compose restart](https://docs.docker.com/reference/cli/docker/compose/restart/).
