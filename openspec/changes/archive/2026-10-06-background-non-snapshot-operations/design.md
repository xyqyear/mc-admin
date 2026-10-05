## Context

See `proposal.md` for the motivation and `docs/snapshot-recovery-roadmap.md` for the separate next round. Relevant current design is documented in `backend/docs/background-tasks.md`, `backend/docs/operations.md`, `backend/docs/servers.md`, `backend/docs/archive-upload.md` and `frontend-react/docs/task-center.md`.

`BackgroundTaskManager.submit_durable` already owns workers, task progress and durable outcome projection. `OperationObserver` already refreshes configuration/files/world views across navigation. Server commands are still awaited by the request; maintenance becomes visible before Docker supplies a container state. Map initialization, manual self-check streaming and archive hashing also have request-owned execution. Recursive deletion and creation/synchronization can spend significant time in filesystem, draining or external-service work.

## Goals / Non-Goals

**Goals:** reuse these boundaries, make acceptance and current activity visible, and move worker lifetime away from UI lifetime. Preserve each feature's validation, blocking interaction and result meaning. Independent backend execution does not imply a nonblocking frontend workflow.

**Non-goals:** a general workflow engine, persistent percentage-event replay, fake progress, broad server locks for ordinary files, automatic mutation retries, or snapshot behavior changes. Browser upload/download bytes, interactive console/RCON and routine queries remain connection-owned. Same-directory rename and small metadata-only configuration conversions stay immediate; they do not launch long filesystem or Docker work.

## Decisions

### 1. Explicit operation inventory

| Operation | Current boundary | First-round treatment |
| --- | --- | --- |
| start/up/restart/stop/down | `servers/commands.py`, request waits for Docker | detached lifecycle task; existing running-intent semantics |
| remove server | lifecycle draining, metadata and recursive removal | detached non-cancellable destructive task; exclude own task from draining |
| create server | lifecycle creation, scheduling, DNS | detached task with immutable validated input and explicit prospective-directory ownership |
| synchronize server registry, including preview | router-owned scan and per-server adoption/deactivation | feature-owned worker with per-server result; preserve OWNER and force protections |
| recursive server/archive deletion | feature application, filesystem thread | detached task with exact path claims and finite cleanup |
| map initialization/forced regeneration | request-owned SSE, download and palette workers | detached task; dialog subscribes to current stage |
| manual self-check, full or individual | synchronous/SSE service | detached task preserving check/run identifiers and findings |
| manual DNS/router update | request-owned external calls | detached task preserving partial/unknown provider outcomes |
| uploaded archive SHA256 | request-owned SSE over upload temporary file | detached task tied to upload identity and lifetime |
| rebuild, populate, compression, ownership, prune | existing durable tasks | audit visibility and completion; retain one task per operation |
| snapshot creation/restore/preview/rollback/maintenance | snapshot/world services | unchanged; next round |

Automatic housekeeping and periodic diagnostics retain their existing scheduler/service lifecycle. A scheduled restart continues to preserve cron skip/outcome history; its maintenance description identifies the scheduled cause. Do not multiply recurring jobs into task-center noise merely to show a lock reason. Snapshot freshness reads performed by self-check do not authorize changing snapshot creation or recovery.

### 2. Feature workers and task submission

Use explicit feature-owned task generators yielding `TaskProgress`; retain domain services as the place where validation, resource ownership and side effects live. Extract map initialization and registry synchronization from routers before adding task adapters. Do not build a callable registry, universal dispatcher or callback framework.

Use a task-submission route for each covered feature action, returning HTTP 202 and the established task identifier shape. Reuse a sensible existing route with the new response or rename it where the task contract is clearer. Backend and frontend deploy together: remove unused synchronous/SSE endpoints, response types and adapters, and migrate all product and test callers. Preserve meaningful validation and authorization, not old wire compatibility. No worker calls a router or retains a request-scoped database session or `UploadFile`.

Capture input values and existing `ServerRef` identities before acceptance. Commit acceptance before acknowledging it, keep validation before side effects, and repeat version/path/identity checks after acquiring execution resources. Keep one execution path per feature, without parallel synchronous and task APIs.

### 3. Preserve resource ownership and avoid duplicate commands

Lifecycle task submission needs atomic conflict detection covering queued and running lifecycle commands, not only the maintenance lock held after the worker starts. Return an actionable busy response with an existing task reference when possible. Do not queue repeated start/restart/remove clicks for later replay. Nonconflicting files keep their path-level concurrency; stop/down retain their intended availability relative to unrelated maintenance.

Create and sync cannot simply pass a server name to today's single-existing-server submission path. Creation reserves the prospective directory and port-allocation resources, records its intended target, and associates the created generation once registration succeeds. It never adopts a same-name directory that appeared after preparation. Synchronization captures the affected identities and reports each adopted/deactivated result, preserving the explicit empty-directory/force check. Extend only the narrow submission/resource representation needed for absent and multi-server targets; never drop parent-scope validation to make these tasks fit.

Removal freezes admission before draining. Its own operation/task identity is explicitly excluded from the drain set, while every other writer remains subject to the existing checks. Failed draining must leave directory removal unstarted. Filesystem execution and finite cleanup stay owned until they settle.

### 4. Progress and cancellation reflect real phases

Use Chinese phase messages such as `正在准备启动`, `正在准备镜像和容器`, `正在停止服务器`, `正在删除服务器文件` and `正在生成地图调色板`. Report image pulling only when actual Docker output identifies it; otherwise retain the broader preparation wording. Existing structured CLI events supply byte/item percentages where available. Do not expose raw subprocess output or secrets through a new progress path.

Task completion means the command and required cleanup finished. The independent server state still reports Minecraft starting/healthy. Never keep a task indefinitely pending solely because a server has no healthcheck.

Initially disable user cancellation for Docker lifecycle/create/remove, registry application, recursive deletion and external DNS mutation. These can leave daemon effects, multi-step changes or non-interruptible filesystem work; the global UI should be honest about this. Map preparation, self-check and hashing can expose cancellation only after tests prove subprocess/input/history settlement. Runtime shutdown continues to drain even tasks without a user cancel button. Existing task kinds retain their current cancellation policy.

### 5. Preserve blocking interactions while reading task status

Inventory each entrypoint's existing loading state, disabled buttons, dialog-close guards, navigation rules and terminal handlers before changing its transport. Preserve those behaviors. A blocking workflow stays blocking from submission through pending/running/finalization; a streaming progress view stays in place and reads the task's stage, progress and result. The product UI polls task status instead of using the original operation request or SSE connection as the execution lifetime. Unused execution streams and their compatibility adapters are removed.

A 202 response only hands observation over to the returned task ID. It must not dismiss a modal, navigate to a success page, enable repeat submission or run the previous completion callback. Derive the initiating view's busy state from both submission and the observed task, with no idle gap between them. Run the existing success/failure/cancellation handling only when the corresponding task outcome is confirmed. A failed poll means observation is unavailable: retain the last known busy state, show a reconnect/retry message and reconcile the same task rather than resubmitting it.

Show an acceptance message in the existing progress surface, or a concise notification where appropriate, without forcing users to leave that surface for the task center. Invalidate task and operation discovery immediately. At the initiating controls show one short live line, for example `正在准备镜像和容器 · 查看任务`. Explain snapshot, cron and recovery maintenance even without a task link. Preserve existing local blocking; resource-level conflict rules must not widen into an unrelated server-wide lock.

Use task detail for the initiating progress view and the active task query across overview/detail/console, including other administrators' work. Do not make component-local `mutation.isPending` represent the entire operation or introduce another task store. Extend feature operation-resource registrations for server/DNS/self-check/upload outcomes. Refresh business queries on all terminal outcomes, including partial failures, through the application observer.

Feature result views retain meaningful data: removal counts, sync per-server errors, self-check findings/run link, and upload verification state. The global task center can close independently. Feature progress panels retain their existing close restrictions; only panels already allowed to close detach observation when closed. Browser refresh, network loss or permitted navigation does not cancel accepted work. After reload, recover the task association and existing blocking state from server task/upload state rather than a component-only task ID. A short-lived task may finish before the first poll, so discovery must include terminal records.

### 6. Upload hashing has an owned input

Tie the hash task to the upload ID and immutable completed temporary file. Keep the input/session alive while hashing; make session expiry and explicit upload cancellation coordinate with the worker. Persist or project the task association through the existing upload status response for reconnect. On return, the browser can resume the current client/server digest comparison and final publication; hashing completion alone does not publish an unverified archive. Final publication also runs as an owned non-cancellable task. Successful publication keeps its session/task association until TTL so a lost acceptance response can reconnect without a second copy. Backend restart marks the task interrupted and preserves existing temporary-upload cleanup rules without pretending that hashing resumed.

### 7. Outcome retention and implementation documentation

Retain the journal as the authoritative bounded record; do not introduce a second task table or persistent raw-event log. Existing task result payloads remain runtime projections and feature-owned histories remain the detail source. Expose interruption honestly when detailed transient results cannot be reconstructed. Keep result links safe and bounded.

Update root/backend/frontend `AGENTS.md` only when implementation actually changes the structure. Then update background tasks, operations, servers, map, archive-upload, self-check, task-center and feature data-flow documentation, plus E2E coverage. The future snapshot requirement record is explicitly prospective and must not be copied into current-state documentation as implemented behavior.

## Risks / Trade-offs

- **A generic wrapper hides unsafe execution ownership** → feature workers keep leases, target checks and cleanup; tests exercise disconnects while real work is gated.
- **Removal deadlocks on its own task** → explicit owner exclusion with regression coverage; no blanket exemption for other tasks.
- **Creation or sync exceeds today's one-server submission model** → explicit prospective/multiple resource identities and race tests; no dynamic unbounded scope expansion.
- **A removed endpoint retains forgotten callers** → update product clients, fixtures, API coverage and browser tests together; audit references and deployed OpenAPI.
- **Indeterminate progress looks stalled** → show current stage and elapsed time, plus honest Docker/readiness wording.
- **Temporary hash input is deleted during work** → owned session reference, coordinated cancellation and expiry tests.
- **A business failure looks like success because the worker returned** → preserve typed feature outcome, check findings and partial-result messages; throw authored execution failures before terminal success.
- **Fast acceptance accidentally unblocks the old UI** → derive busy state through task completion and test modal guards, disabled actions and terminal callbacks during pending/running and failed status reads.

## Migration Plan

1. Add task types, preparation/submission and focused ownership tests; migrate covered endpoints and callers together.
2. Implement lifecycle first, then file/map and administrative/hash workers; audit the inventory before declaring completion.
3. Switch progress observation to task-status reads while retaining existing blocking and terminal behavior; verify close guards, permitted navigation, refresh, reconnect and maintenance feedback in a real browser.
4. Run backend static/focused integration checks, frontend checks, deployed API regressions and snapshot compatibility regressions. No release or push is implied by this change.
5. Roll out backend and frontend together. No schema migration is planned. Application rollback must drain the new workers before switching binaries; never interpret an unknown historical task kind as permission to replay it. Snapshot behavior and data are not migrated in this round.
