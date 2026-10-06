# MC Admin

Web platform for managing Minecraft servers via Docker Compose, with an independent API E2E project:

- `backend/` — FastAPI + SQLAlchemy 2.0 async (see `backend/AGENTS.md`)
- `frontend-react/` — React 19 + TanStack Query (see `frontend-react/AGENTS.md`)
- `e2e/` — standalone Go executable, real deployed API smoke/regression tests and owned Docker environments (see `e2e/AGENTS.md`)

The application ships as a single Docker image (`Dockerfile` at the repo root); the backend serves the built frontend as static files in production. The E2E runner is built separately. Base images are pinned by digest, and runtime layers keep Python dependencies, backend code, frontend vendor chunks, workers, fonts, styles, and app chunks separate so pulls reuse unchanged blobs.

The production image starts Uvicorn at INFO level; protocol DEBUG frame logging can expose WebSocket login credentials, including abbreviated ticket values.

The backend uses an application factory and a per-application runtime for database, configuration, tasks, events, schedulers and clients. Its 35 typed lazy resource properties distinguish an uninitialized sentinel from disabled `None` and empty containers. Startup reconciles interrupted work before opening write admission; shutdown drains producers and writers, then closes the current cached resource instances. Tests bind independent runtimes and temporary data. The supported deployment has one backend writer for each database and managed server directory; see `backend/docs/runtime.md`.

`backend/app/configuration` owns immutable preparation, version-aware Compose/template application, matching source metadata and recovery evidence; server lifecycle and HTTP routes use this boundary. The frontend's application-level operation observer refreshes configuration, server, file/world, snapshots/history, self-check and DNS queries for terminal outcomes independently of the initiating editor page, with session-scoped deduplication and reconnect recovery.

File, archive and snapshot application services declare their filesystem resources before execution. Snapshot scope contracts and retained restoration history belong to `backend/app/snapshots`; history binds to server generations. World adapters separate selection planning, scope execution and finalization. Repository references protect active operations and valid file/map previews from destructive maintenance. Prune previews carry a version of their inputs and own their retained geometry and claims artifacts. The frontend `features/backups` owns common snapshot contracts, commands, observation and history/progress UI; `features/files` and `features/world` compose it alongside their domain controllers; the application operation observer refreshes affected file/world queries across page changes. See `backend/docs/world-restore.md`, `backend/docs/chunk-prune.md` and `frontend-react/docs/data-architecture.md`.

Player log, RCON and heartbeat producers share one runtime-owned identity/session service. `backend/app/players/identity.py` supplies pure UUID syntax normalization; online-mode checks and network resolution belong to the identity resolver. Dynamic configuration exposes seven typed properties that read their owning manager's current cache. Cron uses public server commands and reports configured state separately from scheduler registration. Connectivity plans DNS and router changes independently and exposes unknown provider state without inferring deletions. Identity, settings and health checks capture their owning dependencies; the composition root uses explicit factories and typed accessors with no implicit default runtime.

Persistence and API DTOs belong to their feature modules; `backend/app/db/metadata.py` explicitly registers tables for Alembic. Complete identity DTOs are generated from an isolated OpenAPI document, while event and task-result validators remain explicit. Frontend features own contracts, concrete query/mutation hooks, commands and UI; `app/` composes routes and operation synchronization, and `shared/` holds transport and generic UI. The players feature exposes a pure identity helper shared by profile and map consumers. The world controller groups server, map, claims and players state; dimension selection, initialization and player-list presentation use three concrete components. Architecture checks enforce imports. User-facing version entries live in `frontend-react/src/app/version/config.ts`.

## Prerequisites

Beyond what `pyproject.toml` / `package.json` declare:

- Docker Engine + Docker Compose on the host (the backend manages user MC servers via docker-compose)
- `fd` — required for file search and world layout discovery; pinned by `FD_VERSION` in `Dockerfile`
- Restic — invoked as a subprocess for snapshots; pinned by `RESTIC_VERSION` in `Dockerfile`.
- `mcmap` binary — pinned by `MCMAP_VERSION` in `Dockerfile`.

Binary path settings (`fd_binary_path`, `restic_binary_path`, `mcmap_binary_path`) and their env vars override discovery. Omitted paths resolve once at startup from `PATH`, then `/usr/local/bin`, then `/usr/bin`.

## Quick start

```bash
# backend
cd backend && uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload

# frontend
cd frontend-react && pnpm install && pnpm dev   # port 3000
```

Frontend dev server proxies `/api` to `http://localhost:5678` (see `vite.config.ts`).

## CI

### 交付与测试要求

- 本地只运行改动直接相关、以及受影响调用路径的定向测试，通过明确的测试文件、节点、包或用例筛选限定范围。禁止在本地运行完整项目或任一组件的全量测试，也禁止通过逐目录、分片或多个 subagent 累计执行来变相跑全量。全量测试结果以 GitHub Actions 为准。必要的 lint、类型检查和构建检查仍按各组件要求执行；纯文档变更不运行本地测试。
- 每次项目变更优先在独立分支开发。完成本地定向验证后，必须 commit 并 push 到 GitHub，再对最新提交运行完整 CI；本地通过或部分远端检查通过不能视为完成。
- 完整验证使用 `Qualify and Publish Application`（`.github/workflows/docker-image.yml`）手动触发，指定开发分支并设置 `publish=false`。必须核对同一提交 SHA 的 candidate/Go、static/frontend、全部 backend 分片及覆盖审计、全部 API E2E 分片及覆盖与清理审计、全部 browser 分片及覆盖审计和最终 qualification 均成功。普通 push 自动检查不能替代缺失的完整验证。
- 触发完整 CI 后，确认对应最新提交 SHA 的 run ID，由主 agent 启动一次持久等待命令 `gh run watch <run-id> --exit-status --interval 60 --compact > <log-path> 2>&1`，将输出保存到日志并静默等待命令退出。等待期间不读取日志或进度、不发送进度更新、不开展其他工作；主 agent 和所有 subagent 均不得通过 `gh run view`、`gh run list`、`gh api` 或其他 GitHub 接口重复轮询同一 run 或 job。执行工具分段返回时，只继续等待同一命令；命令退出后才统一读取结果和日志。用户新消息可以中断等待，命令中断或连接失败不代表 CI 已结束或通过。
- 等待结束后统一核对一次提交 SHA、最终结论、全部必需检查及覆盖审计；失败时再读取失败步骤日志，查明原因、定向验证修复、提交、推送并重新完整验证最新提交。不得用旧提交的绿灯、仅重跑局部用例、跳过失败检查或降低业务断言冒充通过。报告需附提交 SHA 和 GitHub Actions 链接；远端完整验证尚未通过时，明确说明尚未通过，不宣称交付完成。
- 每次新增或修改功能，都要按业务行为新增、调整或删除对应测试。测试从用户场景、输入输出、数据副作用、权限、失败与恢复边界验证需求；不得机械复刻实现、只验证内部调用顺序，或照抄生产算法计算预期值。删除旧测试必须有行为已移除、契约已替换或有效覆盖已合并的依据，不能只为让 CI 变绿。
- 功能由同步/流式接口迁移到后台任务时，所有测试调用方和 fixture 都要等待真实任务终态，再验证业务结果；同时覆盖受理不等于完成、重复提交、断线观察、取消/关闭及资源清理。保留独立的业务不变量断言。

- `.github/workflows/backend-tests.yml` collects the actual pytest inventory and derives bounded capability-aware shards from comparable historical phase costs, targeting 300 seconds of execution including fixtures. Independent runners execute each shard sequentially, retain file/shared-fixture groups, upload timings and JUnit, and audit exact node-ID coverage, selection policy and outcomes before combining coverage and publishing timing history. Docker cases require explicit opt-in; external services stay outside ordinary pytest CI. CLI versions come from `Dockerfile`. New tests enter the plan automatically; historical costs affect placement only.
- `.github/workflows/static-checks.yml` runs frontend lint/TypeScript checks/operation-flow tests/asset build, backend Pyright/Ruff, and Go formatting/vet. It uploads Vitest JSON timings and supports both push checks and reuse by release qualification.
- `.github/workflows/candidate.yml` builds one single-platform OCI archive and the race-tested Go runner from a checked source revision. Go test events are uploaded separately from candidate inputs. Candidate metadata records the source fingerprint, archive hash, OCI manifest digest, Docker config digest and runner hash. API and browser jobs consume this artifact.
- `.github/workflows/e2e-tests.yml` globally allocates selected API atomic groups into one matrix, targeting 300 seconds with at most 16 shards and 16 concurrent jobs, each using two workers and one Minecraft slot. Groups with different provider dependencies may share a shard; those dependencies select private configuration and recovery steps. Every API shard uses the unrestricted `dns-e2e` configuration store; provider steps receive credentials only when needed. PR regression, ordinary automatic CI and complete qualification require every current API case except DNSPod. The manual CI profiles are `regression`, `qualification` and `dnspod`; DNSPod alone requires explicit selection and `E2E_EXTERNAL_CONFIG`. Local case/tag selection remains available. Exact coverage, operation observations, candidate identity and local/cloud cleanup are audited before timing publication.
- `.github/workflows/browser-tests.yml` derives explicit Playwright case shards from historical timings and repeated fixture costs. Each shard has an independent owned application/Minecraft environment and one worker; each case has a separate browser context and declared data cleanup. Complete inventory, exact-once execution, candidate identity and owned cleanup are audited before timing publication.
- `.github/workflows/docker-image.yml` qualifies a semantic-version release using the candidate, static, backend, integrated API and browser gates. Promotion copies the tested OCI archive to GHCR with digest preservation and verifies the remote manifest. Prereleases publish their full version and source SHA tags without updating stable aliases. Missing, failed, cancelled or skipped required gates block promotion. See `docs/release.md` for evidence and deployment boundaries.

The 300-second target includes test execution and fixture initialization/cleanup, excluding runner queueing and CI installation. It is not a test deadline. Oversized indivisible units and fixed overhead remain valid and are reported. Each test family permits up to 16 concurrent shard jobs and freezes its latest compatible audited historical snapshot across trusted repository branches in one immutable plan; missing/incompatible history uses positive fallback costs, and failed or incomplete executions cannot replace successfully audited history.

Standalone branch/PR workflows cancel superseded runs within component-specific concurrency groups. Manual qualification and reusable release children have distinct run-scoped groups. See `docs/ci.md` for scheduling budgets, timing evidence and non-publishing qualification.

## Cross-component conventions

- AGENTS.md files describe **current** state; never write changelog-style notes ("recently added X", "previously did Y", "now uses Z").
- New backend features and fixes that change observable behavior require API E2E coverage in `e2e/suites/` and an update to `e2e/docs/coverage.md` in the same change. See `e2e/docs/architecture.md` for isolation, environment composition and extension contracts.
- User-facing application text is Chinese, including frontend UI copy and backend-provided names, descriptions, errors, and messages that may be displayed to users.
- Long-form design background — business logic, invariants, lifecycle ordering, component graphs — lives in `backend/docs/`, `frontend-react/docs/` and `e2e/docs/`. Each `docs/<topic>.md` is self-contained, current-state, no changelog. AGENTS.md carries day-to-day rules and points at the doc.
- `.agents/skills/` contains generated Codex skills and repository-specific skills, including `gen-version-message`. Do not hand-edit generated `openspec-*` skills; run `openspec update` after upgrading the CLI.
- `openspec/specs/` is the source of truth for observable behavior. Administration compatibility, operation consistency and operation recovery have separate contracts. Active proposals and implementation plans live under `openspec/changes/`; completed changes are retained under `openspec/changes/archive/` after their specs are synced. Keep technical design rationale in the corresponding component's `docs/`.

Non-snapshot management work uses feature-owned background workers and task acceptance; blocking interfaces retain their original completion guards while observing task status. Manual global/project/path/world snapshots and restoration/rollback use common durable tasks and generation-bound restoration history. World selection and chunk merging are adapters; preview preparation, cleanup and repository maintenance also use durable tasks. See `backend/docs/non-snapshot-operations.md`.

Schema `2026100600` stores snapshot notes by repository configuration ID and full snapshot ID. The operation journal retains task result payloads; terminal details survive dismissal and backend restart within journal retention, while summary reads omit payloads. File batches share normalized scopes; browser folder exports stream authenticated, generation-bound files into an authorized local directory. Server population prepares a complete tree and publishes it with an atomic Linux directory exchange on the destination filesystem. See `backend/docs/background-tasks.md`, `backend/docs/files.md` and `frontend-react/docs/file-operations.md`.

Snapshot recovery behavior is specified in `openspec/specs/snapshot-recovery/spec.md`; `docs/snapshot-recovery.md` describes current behavior and deployment boundaries. The completed implementation checklist and design are retained under `openspec/changes/archive/2026-10-06-unify-snapshot-recovery/`. Schema `2026093000` preserves legacy world history and refuses downgrade while restoration records remain; see `e2e/docs/deployment-rehearsal.md` for verified upgrade and checkpoint recovery boundaries.
