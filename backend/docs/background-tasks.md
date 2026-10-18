# Background tasks

The runtime owns a `BackgroundTaskManager` and a durable operation journal.
任务覆盖服务器启停/下线/删除/创建/登记同步、文件和压缩包删除、地图初始化、手动自检、手动 DNS/router 更新、上传 SHA256 和发布，以及压缩、填充、重建、所有权修复和区块清理。功能模块拥有 worker；路由只做鉴权、准备和提交。手动快照、恢复、回滚及其预览由 `app.snapshots` 提交统一持久任务，持有目标与仓库引用；恢复与回滚在修改目标前保存安全快照和恢复记录。

执行入口返回 HTTP 202 和 `{task_id}`。查询 `/tasks/{id}` 获取阶段、进度、结果和错误；任务摘要不包含详细结果。已废弃的自检和 SHA256 SSE 执行接口不存在。`submit_durable` 在返回之前提交 journal，`submit` 是 manager 内部的执行登记入口，也用于无 journal 的隔离单元测试。接口清单与 UI 约束见 [非快照操作](non-snapshot-operations.md)。

```python
async def my_operation() -> AsyncGenerator[TaskProgress]:
    yield TaskProgress(progress=0, message="正在开始")
    await perform_owned_work()
    yield TaskProgress(progress=100, message="操作完成", result={"file_count": 42})

result = await task_manager.submit_durable(
    task_type=TaskType.ARCHIVE_CREATE,
    name="压缩存档",
    task_generator=my_operation(),
    server_id="survival",
    actor_id=user.id,
    cancellable=True,
)
```

`SubmitResult` contains the task ID, current task model and a
`Future[TaskResult]`. Progress stays in memory. Feature-specific result payloads
are saved in the journal before being published; acceptance, phase, outcome and
recovery evidence remain separate from the payload.
A captured `ServerRef` binds delayed work to a registered server generation and
confined paths. Acquiring an operation lease revalidates that identity before
execution. Detached work does not inherit its parent's operation ownership.

## Live observation

Authenticated `GET /api/tasks/events?operation_cursor=...` shares one SSE
connection for task, operation and execution-domain observation. The first data
frame is `{"type":"snapshot","tasks":[...],"active_restorations":[...],"prune_states":[...]}`.
Task changes use `{"type":"upsert","task":...}` and
`{"type":"remove","task_id":"..."}`. Summaries retain nullable fields,
including feature-owned `progress_details`. Non-null progress details replace
the complete current details; omission retains them. They are current state,
not a durable progress log.

Event task models add `result_included` and `result`. Running tasks always send
false and null, including at 100 percent. After worker cleanup and journal
confirmation, known terminal results whose JSON encoding is at most 16 KiB
(including null) are included. Larger and unloaded historical results remain
excluded and require one authoritative detail read before completing a
result-consuming workflow. HTTP task lists continue to omit results.
Inline eligibility is privately cached for the settled result object, so each
observer or reconnect does not re-encode an excluded large result. Running and
unknown results do not populate this cache; loading a different result requires
a fresh size decision. The cache is absent from persistence and wire schemas.

`operation_changes` frames carry the existing bounded journal change batch and
cursor/reset contract. Subscribers provide their last successfully handled
cursor on reconnect; notifications wake ring reads after commit without another
queue or HTTP polling. `restoration_index` and `prune_state` frames replace their
respective complete indexes. The router injects the asynchronous domain snapshot
provider; task core does not import snapshot or world services. A provider
failure ends the stream for reconnect and cannot masquerade as an empty index.

Each connection retains at most 256 dirty task IDs and coalesces intermediate
updates. Overflow replaces pending updates with a current-state snapshot. The
publisher never waits for the connection or queries the database. Idle streams
send a comment keepalive every 15 seconds. Reconnecting starts with a fresh
snapshot; the operation cursor does not reconstruct intermediate task progress.
Domain dirty flags are cleared before awaited reads, preserving notifications
that arrive during a read. Disconnecting releases task and journal listeners
only, and runtime shutdown closes subscriptions after draining workers.
Existing HTTP list, detail, cancellation and dismissal endpoints remain available.

Workers can call synchronous `update_progress(task_id, TaskProgress(...))` for
progress callbacks. It updates memory and notifies observers, returning false for
unknown or settled tasks. Callbacks can supply progress, message and structured
details; generators retain the existing durable result-before-publication path.
Reporting 100 percent does not settle a task. Domain owners call synchronous
`notify_observation("restorations" | "prune")` after acceptance and lifecycle
changes. The manager also notifies restoration start/settlement and prune
start/progress/settlement; publishers never await domain reads or observers.

## Cancellation and completion

Cancellation sets `cancel_requested` and directly cancels the owned worker, so a
silent subprocess or an operation waiting for a lease need not yield progress.
The visible status stays `RUNNING` while cleanup runs. Repeated cancellation is
idempotent. Cancelling a queued task prevents its generator from executing.

Generators close nested streams with `aclosing`. `operations.finalization`
protects finite cleanup against both asyncio and AnyIO cancellation, including
waiting for filesystem threads that have already started. Owned subprocesses
start behind a gate: identity registration commits before the command executes.
Cleanup signals only verified process handles, escalates from TERM to KILL and
awaits pipe drainage and process exit. Unverifiable remaining writers retain
recovery evidence and block the affected resource; they cannot publish success.
See [operation ownership](operations.md) for Linux identity and restart recovery.

The manager closes the generator and confirms the journal's terminal outcome
before publishing task status or resolving its future. A late cancellation
cannot overwrite an already committed success. Unexpected failures use a generic
Chinese error and safe type/stack diagnostics; authored `PublicOperationError`
messages remain visible. Cleanup errors remain failures, and filesystem refusal
can leave partial output for inspection.

Deletion excludes its own operation ID, freezes new writers, cancels other tasks and waits for their futures without
holding execution leases. Unsettled tasks or request-owned writers reject
deletion; only a drained, validated deletion permit authorizes removing files.
Runtime shutdown stops submission and drains its workers, including tasks that
are not cancellable through the user API.

## Durable history and compatibility

The public task statuses remain `pending`, `running`, `completed`, `failed` and
`cancelled`. Startup reconciles interrupted operations before admitting writes,
then projects task journal records into the existing task center. Interrupted
work appears as failed with an interruption message and is never replayed.
Historical progress is not reconstructed. Task details read retained result
payloads on demand after restart; older records without a saved payload return
null. The detailed operation API retains the internal state, phase and recovery references.

Task detail and summary include optional `error_code` alongside the existing
string `error`. A configuration version conflict discovered after acceptance
produces `failed` with `error_code="configuration_conflict"`; restored task
history preserves that journal failure code. The code lets an editor retain its
draft and reopen comparison without parsing translated error text. Preflight
configuration conflicts still use an HTTP 409 response before task submission.

`SERVER_REBUILD` runs the configuration application service with its immutable
prepared content and source metadata. File replacement, source commit and
restoring the original running intent belong to the worker, not completion
callbacks. An initially stopped server remains stopped. Failure settlement and
necessary staging cleanup finish while maintenance ownership is still held;
partial application can therefore report failure with a visible recovery block.
See [configuration](configuration.md) for phases and recovery evidence.

File and world recovery return a common task ID and restoration ID. Task acceptance retains target and repository references; safety evidence must be durable before writes. Disconnection only detaches observation. Explicit cancellation waits for owned writers, cache finalization and history settlement before publishing a terminal task result. Unknown writers retain recovery blocks. Active restoration discovery uses the database journal independently of repository availability; pages can resume observation after reload.

Deleting or clearing completed task entries dismisses the current in-memory
projection. Detail reads remain available to observers through the journal and
do not reinsert dismissed entries into the list. Retained records can appear
again after restart. Journal retention bounds the result lifetime and never evicts unresolved
recovery material merely to admit another task.

The frontend's application-level operation observer uses terminal journal
outcomes to refresh registered configuration, task and server queries after
success, failure, interruption or cancellation. It deduplicates handled operation
IDs, catches up after reconnect and clears its session state at logout. Leaving
the editor page does not suppress this synchronization or cancel a detached task.

## API and modules

Every `/api/tasks` route requires a current user; cookie mutations also require
CSRF. Both admin and owner users can access task history. Lists omit `result`;
`GET /api/tasks/{id}` provides current or retained detail, returning 404 when the
record is absent or has expired. Cancellation uses
`POST /api/tasks/{id}/cancel`; single and bulk `DELETE` dismiss terminal entries.

`manager.py` owns submission, workers, cancellation and projection;
`models.py` defines `BackgroundTask`; `types.py` defines task kinds, statuses,
progress and results. `get_tasks_by_server_id`, `get_future` and
`get_active_tasks` expose the owned work needed for lifecycle coordination.

`tests/operations/test_execution.py` verifies silent cancellation, queued
cancellation, repeated cancellation during thread cleanup, gated process
registration, pipe pressure, terminal publication and late cancellation.
`tests/test_runtime.py` verifies application isolation and ordered shutdown.
