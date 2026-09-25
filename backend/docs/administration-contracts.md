# Administration compatibility contracts

This inventory describes the supported user journeys for the application-boundaries refactor. The route and schema baseline is `tests/contracts/fixtures/api-contract.json`; its executable comparison lives in `tests/contracts/`. The independently deployed API scenarios and their exact case IDs are catalogued in `../../e2e/docs/coverage.md`. A route snapshot detects accidental contract changes; it does not prove authorization or business behavior.

## Common boundaries

The browser uses a signed, HttpOnly session cookie and CSRF protection for mutations. Operational clients may use the configured master bearer token. Both admin and owner accounts can administer servers and task history; owner-only account/settings operations retain their explicit guards. Anonymous/invalid sessions fail before protected resource mutation. Detailed route dependencies are captured in the API fixture; authorization inside handlers is also covered by `e2e/suites/auth`, `system`, `archive/permissions.go` and `cron/cron.go`.

HTTP status codes, cookie names, public server IDs, route paths and documented payloads remain compatibility boundaries. Expected errors retain `detail` as either a string or a structured object, including resumable upload offsets. Validation failures retain a string `detail` with status 422. Unexpected request errors return a generic Chinese 500 message; logs retain the exception type and stack locations without exception values, query strings or headers. Frontend consumers use the normalized `ApiError` fields and retain structured `detail`.

## Journeys and regression owners

All paths below are relative to `/api`; the fixture includes individual methods and routes.

| User journey | Observable contract | Regression owner |
| --- | --- | --- |
| Sign in, use login code, sign out | Password and WebSocket code login preserve cookie/CSRF flow, account identity and revocation. A network/5xx failure while loading the current user offers retry without losing the requested page. | `tests/test_auth_session.py`, `tests/test_login_code_logging.py`, `tests/test_safe_errors.py`; `e2e/suites/auth/`; frontend `App.test.tsx` and HTTP/query tests |
| Manage users and settings | Owner restrictions, secret masking and dynamic configuration validation remain. Invalid updates preserve the previous configuration; background refresh does not replace an edited draft. | `tests/dynamic_config/`, `tests/test_audit.py`; `e2e/suites/system/`; frontend configuration tests |
| Discover/create/adopt servers | `/servers/` remains DB-driven; filesystem reconciliation is owner-only with dry-run, empty-mount safety and removed-row history. Direct/template creation retains port validation and optional restart scheduling. | `tests/servers/`, `tests/templates/`; `e2e/suites/servers/` |
| Start/stop/restart/remove | Existing operation names and stopped/running intent remain. Start, rebuild and scheduled restart share maintenance ownership. Delete cannot remove a directory with unsettled writers. | `tests/world/test_operation_races.py`, `tests/servers/test_lifecycle.py`; `e2e/suites/minecraft/`, `world/maintenance.go`, `world/delete.go` |
| Edit Compose or template parameters | Raw YAML, comparison, template snapshot retention and mode conversion remain. Initial loading cannot create an empty draft; remote refresh/comparison and failed saves preserve edits. Untouched direct/template sessions follow refreshed server state, including task completion across navigation. Conversion retains its captured baseline because its form draft has separate ownership. Intentional reset loads the current remote baseline. | `tests/templates/`, `tests/servers/`; `e2e/suites/servers/regression.go`; frontend Compose tests and `browser/journeys.spec.ts` |
| Edit reusable templates | Definitions, defaults, expressions, validation and server-retained snapshots remain. Loading and mutation failures preserve authored fields. | `tests/templates/`; `e2e/suites/templates/`; frontend template editor tests |
| Browse/edit/search/upload files | Confined paths, names, regex/deep search, download, rename, ownership repair and overwrite/partial upload policies remain. File save requires a successful load; a deliberately emptied loaded file is valid. Failure keeps the editor open. | `tests/files/`; `e2e/suites/files/`; frontend `ServerFiles.test.tsx` |
| Upload/compress/populate archives | Resumable offsets/expiry/hash events and final content remain; a failed task cannot be reported as success. Server-linked tasks are rejected during deletion admission freeze. | `tests/archive/`, `tests/test_decompression.py`; `e2e/suites/archive/`, `tasks/` |
| Track and cancel background work | Summary lists omit large result details; details and server state endpoints retain their payloads. Page navigation leaves tasks running. Cancellation closes the generator and child process before the terminal state is visible. | `tests/background_tasks/`, `tests/servers/test_lifecycle.py`; `e2e/suites/tasks/`, `archive/`, `world/` |
| Back up and restore files | Snapshot coverage, ignore rules, retention, time restrictions and safety snapshots remain. Ordinary file restores remain available online. Full-server/world writes require stopped state; maintenance conflicts are explicit. | `tests/snapshots/`, `tests/world/test_maintenance.py`; `e2e/suites/snapshots/`, `world/maintenance.go` |
| Selectively restore and roll back worlds | World/dimension/region/chunk scopes, sidecars, preview expiry and retained safety references remain. History binds to the original server generation and can restore a missing range and undo that rollback. Empty snapshot selections remove only selected content, respecting ignores. Closing SSE cancels the request-owned operation and finalizes any established history; temporary leases are released only after writers stop. Cancellation before a completed safety snapshot/history does not promise rollback, and unconfirmed writers retain recovery blocking. Restart marks interrupted history. | `tests/world/`, `tests/snapshots/test_empty_restore.py`; `e2e/suites/world/restore.go`, `restore_generation.go`, `maintenance.go` |
| Render maps, inspect claims/player positions, prune chunks | Dimension/layout support, cache/geometry contracts, safe reads and stopped-state pruning remain. Prune and restore cannot overlap startup/rebuild/restart; actual map writers own cache/file resources. Expired, changed or consumed prune previews cannot authorize another apply, and active readers/applies retain their preview artifacts. | `tests/mcmap/`, `tests/ftb_claims/`, `tests/player_locations/`, `tests/world/test_prune_validity.py`; `e2e/suites/world/` |
| Configure server restart plans and custom cron | Server-managed plan lookup uses exact ownership. Prefix-related servers and independently named cron jobs cannot be read or changed accidentally. Ambiguous legacy managed plans return 409 without mutation. | `tests/cron/`, `tests/servers/test_restart_schedule_identity.py`; `e2e/suites/minecraft/schedule.go`, `cron/` |
| Observe players and history | Identity resolution, filtering, chat/achievement cursors and post-commit events remain. Concurrent repeated joins yield one open session; repeated leaves preserve the first recorded end time and duration. | `tests/players/`, `tests/migrations/`; `e2e/suites/players/` |
| Use console, RCON and external events | WebSocket connection/disconnection, console IO, RCON validation, in-game messaging and SSE envelope/cursor behavior remain. Streams are not replaced with background task polling. | `tests/events/`, `tests/servers/test_bot_integration_routes.py`, `tests/test_websocket_console.py`; `e2e/suites/minecraft/`, `players/`, `auth/` |
| Inspect health/resources, reconcile DNS/router | Health categories, failure isolation, runtime dynamic settings and DNS provider reconciliation/deletion policies remain. External qualification stays explicit and requires owned test domains. | `tests/self_check/`, `tests/dns/`, `tests/test_monitoring.py`; `e2e/suites/selfcheck/`, `system/`, `dns/` |

Test paths in the table identify the owning suites; `rg --files tests` and the collected capability manifest provide the concrete test identities. The E2E coverage document tracks remaining breadth gaps separately from unit-test coverage.

`../../frontend-react/browser/journeys.spec.ts` connects the relevant contracts
through a real browser and owned deployed application: file load/save failures
and deliberate empty saves, stale Compose confirmation and comparison, task
completion after navigation, session retry/logout/login and console reconnect,
interrupted restoration with retained recovery history, and expired prune
confirmation without a world write. Transport faults are injected at the
browser/proxy boundary; successful writes, task outcomes and recovery references
are checked through the real API and owned filesystem. These cases complement
the broader deployed API suites and do not replace them.

`../../frontend-react/browser/00-observations.spec.ts` records overview polling,
navigation and cold/warm map requests. Fixed-binary and deployed upload/backup
comparisons are documented in `workload-measurements.md`. Counts are diagnostic;
correct final content, explicit failure feedback and retained recovery options
remain the acceptance criteria.

## Persistent and deployment contracts

Production remains one image serving the SPA and API with one writer process.
Configuration, SQLite, server directories, archives, Restic repository and log
mount paths retain their meanings. The per-application runtime owns dependencies
and shutdown; the durable operation journal records ownership and recovery
evidence. Configuration, file/archive/snapshot and world application services
declare their resource scopes. This does not provide multi-worker deployment.

Schema migration runs before DB consumers start. The supported release fixture
is generated from the actual `v5.3.0` source and contains synthetic data, never
user exports. Duplicate open player sessions block the uniqueness migration
before DDL; the offline preflight/repair process in `database-migrations.md`
requires an explicit database path and reviewed report, preserves session IDs,
and writes durable repair evidence. Startup reconciles interrupted ownership
before producers and writes. Server generations bind managed plans and
restoration history; uncertain historical ownership is retained without
reassignment. Downgrade guards preserve unresolved operation evidence and
identity protection; schema rollback never automatically undoes user data edits.

Binary versions, synthetic fixtures and workload commands are documented in `testing.md`. Baseline timings are measurements tied to their environment, not arbitrary performance pass/fail thresholds.

Release qualification consumes one OCI artifact and one recorded API runner.
Static, backend, API and browser checks must all pass for the same source before
the artifact can be promoted; the remote OCI manifest must match the tested
manifest. A Docker image config ID identifies the locally loaded configuration
and is recorded separately from that registry digest. See
`../../docs/release.md` for candidate metadata, failure gates and deployment
rollback boundaries. A local protocol rehearsal does not represent a GHCR
release or permission to replace a deployed user's data.

## Intentional corrections

Intentional corrections cover wrong-server schedule/history reuse, duplicate
open sessions and repeated-leave duration changes, unsafe maintenance or file/cache
overlap, deletion despite unsettled writes, credential-bearing error output,
lost editor drafts, false refresh success and login redirects caused by temporary
errors. Console connection waits for both terminal readiness and an eligible
server state, regardless of response order; losing eligibility closes the socket
and its retry timer. Configuration versions detect stale saves. Prune input versions reject
stale/repeated authorization; preview references prevent premature cleanup.
Empty world selections restore their actual absence and retain reversible
history. These corrections have owning regression tests above; other supported
behavior remains a compatibility target.
