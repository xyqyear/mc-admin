# Persistence/business test governance — final reconciliation

Initial per-file audit: audit-persistence.md. This final report records actual implementation and retention decisions, not further proposed work. Scope: all tests under players, cron, dynamic_config, templates, servers, self_check and configuration. Production behavior unchanged.

## Implemented

- Ordinary independent file/in-memory engines and handwritten sessionmakers now use shared Runtime-owned production Database fixtures. All players create_test_db/cleanup_test_db callers migrated and obsolete helpers removed. The only remaining custom async_sessionmakers in these domains are two deliberate concurrency-instrumented AsyncSession subclasses, inheriting every production factory option.
- HTTP, services and workers share one session factory; individual service calls create independent sessions. Removed request-only get_db/service-get_async_session patches. API clients construct independent create_api_app(current_runtime()) and close contexts, without starting production root external producers.
- Cron managers/registries are function-owned. Removed module-level mutable manager/registry. Recovery tests register every manager shutdown in AsyncExitStack so one failing shutdown cannot skip remaining cleanup. API fixture initialization/shutdown is protected by finally.
- Cron sleep(2/3) success guesses became real terminal-history observation, exact execution IDs/counts and expected outcomes. Calendar fire times replace internal trigger.fields indexes. Scheduled commands still dispatch through real APScheduler. The shared run_scheduled_once helper replaces only the live trigger with a one-shot DateTrigger before yielding control; persisted schedules start two UTC calendar days ahead, preventing dispatch during DB/recovery awaits before replacement. It preserves persisted cron configuration, dispatched arguments, exact counts and execution IDs. This removes recurring-second races during slow CI and after manager restart.
- Players removed fake 200ms network delays. Advanced integration uses real ConfigManager values; RCON observes real reconciliation completion and heartbeat waits on committed SQL changes. Continuous heartbeat intentionally uses the valid minimum ten-second interval. Skin substitution is at the external fetch-client boundary and lasts through owned-work drain, rather than replacing update_player_skin.
- Added preview→changed ignored-prefix configuration→delete scenario proving current candidates are recomputed and newly nonmatching users survive.
- Two template-conversion fake submit_durable/manual-SHA256 tests now execute real journal-backed tasks and wait for terminal success, inspect committed source/variables, actual Compose bytes, task HTTP status and staging cleanup. Real execution exposed invalid old fixture container names; valid inputs now agree with public server identity.
- Template migration, server creation and template-config API fixtures bind the production OperationJournal before the task manager is constructed. Fresh independent journal reads verify SUCCEEDED/writers_stopped/actor on migration and creation; creation also checks committed template snapshot/values and exact Compose. This closes the API-app-without-lifespan in-memory task-manager bypass found in independent review.
- Template/default-variable CRUD reads back saved contents; invalid defaults preserve prior state; template deletion returns subsequent 404; listing checks exact contents.
- Server list/detail/overview now use real SQL rows and Compose files; only Docker status is substituted. Orphan folders stay outside managed listing, drifted rows are skipped, stopped-server stale players hidden. Removal verifies target player closure/duration, other-server session preservation, directory removal and retained tombstone.
- Server lifecycle/sync and advanced player patch scopes use ExitStack; teardown stops managers before restoring resources.
- Self-check events now execute real owned work/service and verify persisted trigger/user/run/findings. Disabled/unavailable triggers leave no runs. Progress runs two real checks, holds the second check at an explicit gate, observes intermediate findings without a terminal DB result, then verifies completion persistence.
- Cron real-Restic tests use runtime_config rather than partial SimpleNamespace configuration. Existing coherent Runtime schema initializers remain explicit schema setup, not additional databases.
- Main agent completed delegated dynamic_config work: public schema-version/registration behavior, fresh ConfigManager reload on update/reset, invalid-rule database preservation. Main agent owns documentation corrections for current logical-name cron scheduling.

## Retention decisions closing the initial audit

- Template variable type/range/bool-vs-int/regex/default and JSON Schema tests protect product-owned editor/save contracts. YAML order/type/invalid cases control whether a rebuild is necessary. They remain cheap independent examples; no edge was deleted to reduce count.
- Weekday normalization and executable fire-time tests protect accepted syntax versus calendar meaning. Compound Sunday/list/range/step coverage remains.
- Basic cron registry/schema/custom typed parameters protect the extension contract. Helper class location remains cosmetic; mutable manager and registry isolation is fixed.
- Player CRUD/query tests may retain caller-owned Sessions where the function explicitly accepts that unit of work. Service/concurrent producer tests independently read actual committed state, eliminating the former shared-service-session weakness. Ongoing-playtime assertions intentionally tolerate real clock advancement without timing sleeps.
- Mojang/skin/cache/profile tests keep inaccessible external API substitutes. Real usercache files, SQL and stream cleanup remain. Typed PlayersConfig instances for isolated filtering cases remain controlled domain inputs; real persistence/dynamic updates are independently verified.
- SQL subclass gates reproduce concurrency deterministically while retaining real independent file-SQLite connections. They are scheduling controls, not database mocks.
- Synthetic self-check definitions remain useful for aggregate/retention and fault semantics, alongside real game-port, binary dependency, files/JAR/fd and SQL paths. UID mismatch uses a narrow stat override to avoid requiring root-only chown; actual fd and filesystem scan still execute.
- Current self-check baseline/patch/disabled/tie-break cases remain separate user-visible historical projections.
- Configuration durable-phase injections remain because outcomes include actual files, metadata, terminal history, recovery blocks and cleanup. Real Docker rebuild remains untouched and capability-gated.
- Real Restic job/history/repository coordination tests and server/global lock variants remain. Snapshot restoration contents are independently protected by resource-domain tests. Error-safety tests retain narrow exceptions to verify status/secret boundaries.
- Initial suspicion about template preview setup was false: create_template_server already awaits task_result before returning its 202 response. No duplicate wait needed.
- Generation/path/symlink/creation compensation/stale trigger/managed logical-name/optimistic version tests retain all business boundaries.
- No low-level pure test was removed just for calling a low-level method. Broad schema/parser assertions are retained where they are the actual product contract, rather than application code reimplemented in a test.

## Validation performed

No component/directory suite was run. Explicit changed files/nodes only:

1. Representative player join/chat, cron create, template create, server sync, dynamic config update: 6 passed.
2. New self-check event/progress, template rebuild, cron failure/count recovery, player RCON/heartbeat/concurrent join: 9 passed, 2 initial template failures. Fixture name/helper API corrected; exact two failed nodes rerun: 2 passed.
3. Server list/detail/overview/removal, calendar scheduling, cron API/recovery, default-variable update/rejection, cleanup recomputation, ignored RCON, finished playtime: 14 passed.
4. Ruff for players/cron/templates/servers/self_check/configuration passed. Pyright same paths: 0 errors, 0 warnings. git diff --check passed. Final narrow backup-config/AsyncExitStack cleanup changes passed Ruff; Subsequent independent cross-review identified the recurring-schedule race; the single-fire correction passed the two affected failure/count-recovery nodes (2 passed), with no suite expansion.

5. Final durable-journal correction: two conversion nodes passed; server creation and template-config readback nodes passed (2 + 2). A collection-only wrong enum import was corrected before the two conversion nodes ran. Latest narrow Pyright/Ruff recorded separately.

Logs: /tmp/persistence-second-tests.log, /tmp/persistence-template-retry.log, /tmp/persistence-final-tests.log, /tmp/persistence-pyright-final.log, /tmp/persistence-single-fire-tests.log. Main-agent dynamic-config validation is separate. No commit, push or CI performed here. Latest-SHA full qualification remains main-agent delivery work.


## Independent cross-review of resource domains

Reviewed actual diffs and coverage successors in operations, snapshots/world, archive, mcmap, FTB claims, player locations and background tasks. Real archive HTTP→7z→extraction→fresh journal assertions retain unselected data and terminal semantics. Real SNBT/NBT fixtures test domain decoding, corrupt input and source preservation; region fixtures test selected mutations and untouched chunks. Shallow fake success/argv duplication is covered by those actual binaries; oversized/error/cancel protocol coverage remains. World manually assigned ORM final-state/rollback rows are replaced by existing command/history restore-and-rollback outcome cases, including absent sidecars and negative coordinates. Runtime-owned shared DB and try/finally teardown are coherent.

One P2 finding handed back to resource owner: new cache-owner test uses the same OS user for data and child creation, so owner equality passes even without chown, while the root adapter test was removed. Requested restoring narrow privileged adapter coverage or creating genuinely different owners. Resource agent owns correction and final verification; no resource code edited by this reviewer.

No other material resource-diff findings. No further implementation pending in this agent's seven domains; changes frozen after final static checks. Parent owns full qualification and final report.
