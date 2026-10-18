# Task Center

The globally mounted task center displays backend tasks and browser downloads across page navigation. `features/tasks/` owns task DTOs, transport, observation, commands, downloads and UI. `app/layout/MainLayout.tsx` mounts its public trigger/panel.

## Backend task state

`contracts.ts` contains the HTTP DTO and the camel-case view model; `api.ts` performs that explicit conversion. Backend statuses are lowercase `pending`, `running`, `completed`, `failed`, `cancelled`. Dynamic result objects remain feature-validated where a workflow consumes them.

TanStack Query is the only backend-task state owner. `observation.ts` shares
one authenticated `GET /tasks/events` connection per QueryClient across tasks,
operation refresh and execution discovery. `useTaskFeed` exposes current task,
active-restoration and prune snapshots; domain arrays remain unknown until the
first successful snapshot. Late consumers use the same cache and connection.
Connection bookkeeping contains no second task store.

Task summaries carry nullable, size-bounded `progress_details`. Map stages, bounded
cumulative self-check findings, hash byte counts and batch item counts update
directly from these frames, without intermediate detail requests. Self-check
projections report total/truncated counts when findings exceed the event budget;
complete findings remain in the final result. Snapshot/upsert updates are current
state and may coalesce; they are not a history of every progress change.

There is no periodic task HTTP fallback. EOF, invalid frames and missing keepalive
restart the stream with bounded backoff. Reconnect replaces current snapshots
without submitting work. Disconnected nonterminal detail views expose a reconnect
state while retaining their task identity and data; waiters show a reconnect
warning and keep their busy guard. Reconnection clears the warning.

Event tasks explicitly carry `result_included`. Only genuinely settled terminal
results encoded within 16 KiB, including null, are included. Those results can
complete a waiter directly. Initial or retained details and terminal results
excluded from events use on-demand HTTP. An excluded-result read is shared per
task. `BackgroundTask.status` always retains the real execution status;
`resultReady` separately records whether the complete terminal result has been
read. `useTask` exposes `isAwaitingResult`, `resultError` and `retryResult`.
`TaskResultFeedback` displays result-loading failures and retries reading the
same task without resubmitting work or releasing result-dependent guards.
Dismissing the list entry does not prevent HTTP result recovery. A later
observation or explicit retry can resume a failed read without a retry timer.
Running tasks never carry a settled result. Unobserved event history does not
preallocate detail queries; task-list updates only visit registered list queries.

`subscribeTaskEvents` also retains the shared connection for asynchronous operation
consumers. Batches are processed serially, and only successful consumption advances
the cached cursor used by the next connection. Authentication expiry, cache clear
and subscriber disposal abort old work. The [operation refresh](operation-refresh.md)
owner describes resource invalidation and reset semantics.

Task items render progress/message/error, allow explicit cancellation when a pending/running task is cancellable, and allow terminal records to be dismissed. Mutation controls show pending state and report failures; cancellation acceptance keeps the task active until its real terminal state. The list distinguishes initial read failure, confirmed empty results and disconnected retained state, with explicit reconnect controls. Terminal task details provide an on-demand result view, including self-check findings, per-item failures and expandable complete result data. Navigating away does not discard these server-owned results. The panel shows active tasks and terminal results from the last thirty minutes (records without an end time remain visible); clearing completed records sends the existing task API command.

Within each active or completed group, backend tasks appear newest first by
creation time and browser downloads by start time. Progress updates and completion
times do not change this ordering. Sorting is local to the rendered lists.
Backend task timestamps include their UTC offset, so the thirty-minute display
window and elapsed time do not depend on the browser matching the server timezone.

Manual snapshot creation and file/world restore/rollback, lifecycle,
creation/synchronization, file/archive deletion, map initialization, manual
self-check/DNS and upload hashing/publication return `202 {task_id}`.
`commands.ts` exports `waitForTaskResult`, sharing the same stream and detail
queries as `useTask`. Result-consuming views and waiters retain their running
guard until an included settled event or a successful complete detail read
confirms the outcome. Dismissing a task does not remove its retained detail or result. A waiter
receiving 404 reports a missing/expired record and asks the user to refresh the
relevant page to check the actual outcome. An AbortSignal or the last view
leaving detaches observation without cancelling execution. Authentication expiry
and cache clearing close the old connection and reject late cache writes. Task
acceptance, cancellation acceptance and 100% progress alone never unblock a
workflow.

Server controls show the maintenance reason and a task link when available. Creation, map initialization, self-check, DNS and synchronization also discover active work when reopened. Map initialization retains its non-dismissible progress dialog; existing file/upload forms retain their original busy state and terminal behavior. Browser File objects are not persisted by the task center. `openTaskCenter` opens the background tab without giving feature components ownership of panel state. From inside a modal dialog it opens a separate accessible modal task center, with focus and pointer interaction managed by Base UI; closing it returns to the original workflow. Ordinary page launches retain the floating panel so navigation and downloads can continue.

## Completion ownership

Task commands invalidate task and operation discovery. The application
[operation observer](operation-refresh.md) owns business-cache refresh across
navigation, including partial failures; task/progress panels only present it.
Feature-owned prune metadata and retained recovery results survive generic task
dismissal. The [shared snapshot UI](snapshot-recovery.md) owns recovery-specific
closing guards, active discovery and history observation.

## Client state

- `panelStore.ts`: panel open state, modal launch mode, active tab and drag position. Only the launcher position persists.
- `downloadStore.ts`: browser download records and live AbortControllers. Directory batches retain fixed byte/file totals after scanning, received bytes, saved/failed file counts, destination and bounded failure/name-mapping details. Persisted in-flight records become cancelled on reload because an HTTP download cannot resume from a serialized controller.
- `downloads.ts`: public download command adapter; archives and ordinary files supply the HTTP operation and progress callback. Browser-owned directory export supplies a streaming executor and aggregate progress through `executeManagedDownload`.

Directory-export execution belongs to
[file operations](file-operations.md#浏览器目录导出). The task center displays its
scanning/transfer state, fixed totals, saved/failed counts and name-mapping
feedback. It does not own the picker, manifest or file-writing algorithm.

`ui/TaskCenterTrigger.tsx`, `TaskCenterPanel.tsx`, `BackgroundTaskList.tsx`, `BackgroundTaskItem.tsx`, `DownloadTaskList.tsx` and `DownloadTaskItem.tsx` present these states. The public `ui/index.ts` entry is used by the app shell.
