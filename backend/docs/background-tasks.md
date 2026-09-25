# Background tasks

The runtime owns a `BackgroundTaskManager` and a durable operation journal.
Archive compression, server population, rebuild, file ownership repair and chunk
prune submit async generators through `await task_manager.submit_durable(...)`.
The journal commits acceptance before returning the task ID. The synchronous
`submit(...)` remains a compatibility entry point for isolated callers without a
journal; production routes use durable submission.

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
`Future[TaskResult]`. Progress and feature-specific results stay in memory;
bounded acceptance, phase, outcome and recovery evidence belong to the journal.
A captured `ServerRef` binds delayed work to a registered server generation and
confined paths. Acquiring an operation lease revalidates that identity before
execution. Detached work does not inherit its parent's operation ownership.

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

Deletion freezes new writers, cancels tasks and waits for their futures without
holding execution leases. Unsettled tasks or request-owned writers reject
deletion; only a drained, validated deletion permit authorizes removing files.
Runtime shutdown stops submission and drains its workers, including tasks that
are not cancellable through the user API.

## Durable history and compatibility

The public task statuses remain `pending`, `running`, `completed`, `failed` and
`cancelled`. Startup reconciles interrupted operations before admitting writes,
then projects task journal records into the existing task center. Interrupted
work appears as failed with an interruption message and is never replayed.
Historical progress and result payloads are not reconstructed. The detailed
operation API retains the internal state, phase and recovery references.

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

World restore is a request-owned SSE flow with its own restoration history and
operation journal record. It does not become a detached task. Completion events
are emitted only after required cleanup and journal finalization; disconnects
close owned writers and retain safety snapshot references.

Deleting or clearing completed task entries dismisses the current in-memory
projection. It does not delete operation evidence; retained records can appear
again after restart. Journal retention is bounded and never evicts unresolved
recovery material merely to admit another task.

The frontend's application-level operation observer uses terminal journal
outcomes to refresh registered configuration, task and server queries after
success, failure, interruption or cancellation. It deduplicates handled operation
IDs, catches up after reconnect and clears its session state at logout. Leaving
the editor page does not suppress this synchronization or cancel a detached task.

## API and modules

Every `/api/tasks` route requires a current user; cookie mutations also require
CSRF. Both admin and owner users can access task history. Lists omit `result`;
`GET /api/tasks/{id}` provides current detail. Cancellation uses
`POST /api/tasks/{id}/cancel`; single and bulk `DELETE` dismiss terminal entries.

`manager.py` owns submission, workers, cancellation and projection;
`models.py` defines `BackgroundTask`; `types.py` defines task kinds, statuses,
progress and results. `get_tasks_by_server_id`, `get_future` and
`get_active_tasks` expose the owned work needed for lifecycle coordination.

`tests/operations/test_execution.py` verifies silent cancellation, queued
cancellation, repeated cancellation during thread cleanup, gated process
registration, pipe pressure, terminal publication and late cancellation.
`tests/test_runtime.py` verifies application isolation and ordered shutdown.
