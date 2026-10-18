# Task Center

The globally mounted task center displays backend tasks and browser downloads across page navigation. `features/tasks/` owns task DTOs, transport, polling, commands, downloads and UI. `app/layout/MainLayout.tsx` mounts its public trigger/panel.

## Backend task state

`contracts.ts` contains the HTTP DTO and the camel-case view model; `api.ts` performs that explicit conversion. Backend statuses are lowercase `pending`, `running`, `completed`, `failed`, `cancelled`. Dynamic result objects remain feature-validated where a workflow consumes them.

TanStack Query is the only backend-task state owner. `queries.ts` exposes the
`queryKeys.ts` factories and list/active/detail requests. `observation.ts` shares
one authenticated `GET /tasks/events` connection per QueryClient across lists,
the badge, detail views and initiating workflows. The initial snapshot replaces
current summaries; upserts refresh progress and removals hide dismissed rows.
Detailed results remain in their existing detail cache. Connection bookkeeping
contains no second task store.

A healthy stream disables periodic task-progress reads. Before connection or
after a failure, lists and the badge retain their one-second active/ten-second
idle HTTP recovery; detail observers use two seconds and initiating waiters one
second. EOF, invalid frames and a missing keepalive restart observation with
bounded backoff; reconnect obtains a fresh snapshot without submitting work.
Map initialization and self-check obtain their intermediate result metadata
through event-triggered, coalesced detail reads. Other ordinary progress uses
summary fields directly.

Task items render progress/message/result/error, allow explicit cancellation when a pending/running task is cancellable, and allow terminal records to be dismissed. The panel shows active tasks and terminal results from the last thirty minutes (records without an end time remain visible); clearing completed records sends the existing task API command.

Within each active or completed group, backend tasks appear newest first by
creation time and browser downloads by start time. Progress updates and completion
times do not change this ordering. Sorting is local to the rendered lists.

Manual snapshot creation and file/world restore/rollback, lifecycle,
creation/synchronization, file/archive deletion, map initialization, manual
self-check/DNS and upload hashing/publication return `202 {task_id}`.
`commands.ts` exports `waitForTaskResult`, sharing the same stream and detail
queries as `useTask`. Terminal summaries trigger a complete HTTP detail read;
result-consuming views and waiters retain their running guard until that read
confirms the outcome. Transient read failures show reconnecting and retain the
guard. Dismissing a task does not remove its retained detail or result. A waiter
receiving 404 reports a missing/expired record and asks the user to refresh the
relevant page to check the actual outcome. An AbortSignal or the last view
leaving detaches observation without cancelling execution. Authentication expiry
and cache clearing close the old connection and reject late cache writes. Task
acceptance, cancellation acceptance and 100% progress alone never unblock a
workflow.

Server controls show the maintenance reason and a task link when available. Creation, map initialization, self-check, DNS and synchronization also discover active work when reopened. Map initialization retains its non-dismissible progress dialog; existing file/upload forms retain their original busy state and terminal behavior. Browser File objects are not persisted by the task center. `openTaskCenter` opens the background tab without giving feature components ownership of panel state.

## Completion ownership

Task commands invalidate task and operation discovery. The application
[operation observer](operation-refresh.md) owns business-cache refresh across
navigation, including partial failures; task/progress panels only present it.
Feature-owned prune metadata and retained recovery results survive generic task
dismissal. The [shared snapshot UI](snapshot-recovery.md) owns recovery-specific
closing guards, active discovery and history observation.

## Client state

- `panelStore.ts`: panel open state, active tab and drag position. Only the launcher position persists.
- `downloadStore.ts`: browser download records and live AbortControllers. Directory batches retain fixed byte/file totals after scanning, received bytes, saved/failed file counts, destination and bounded failure/name-mapping details. Persisted in-flight records become cancelled on reload because an HTTP download cannot resume from a serialized controller.
- `downloads.ts`: public download command adapter; archives and ordinary files supply the HTTP operation and progress callback. Browser-owned directory export supplies a streaming executor and aggregate progress through `executeManagedDownload`.

Directory-export execution belongs to
[file operations](file-operations.md#浏览器目录导出). The task center displays its
scanning/transfer state, fixed totals, saved/failed counts and name-mapping
feedback. It does not own the picker, manifest or file-writing algorithm.

`ui/TaskCenterTrigger.tsx`, `TaskCenterPanel.tsx`, `BackgroundTaskList.tsx`, `BackgroundTaskItem.tsx`, `DownloadTaskList.tsx` and `DownloadTaskItem.tsx` present these states. The public `ui/index.ts` entry is used by the app shell.
