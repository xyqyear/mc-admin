# Task Center

The globally mounted task center displays backend tasks and browser downloads across page navigation. `features/tasks/` owns task DTOs, transport, polling, commands, downloads and UI. `app/layout/MainLayout.tsx` mounts its public trigger/panel.

## Backend task state

`contracts.ts` contains the HTTP DTO and the camel-case view model; `api.ts` performs that explicit conversion. Backend statuses are lowercase `pending`, `running`, `completed`, `failed`, `cancelled`. Dynamic result objects remain feature-validated where a workflow consumes them.

TanStack Query is the only backend-task state owner. `queries.ts` owns `taskQueryKeys`, list/active/detail requests and polling. Lists and the badge poll every second while active tasks exist, otherwise every ten seconds; task details poll every two seconds until terminal. The badge reads the active-task query directly. There is no background-task Zustand mirror.

Task items render progress/message/result/error, allow explicit cancellation when a pending/running task is cancellable, and allow terminal records to be dismissed. The panel shows active tasks and terminal results from the last thirty minutes (records without an end time remain visible); clearing completed records sends the existing task API command.

## Completion ownership

`app/operations/OperationObserver.tsx` owns business-cache completion effects through feature resource registries. Configuration, populate/compression/ownership presentation and world restore/prune views display outcomes without owning those effects. Closing independent-task dialogs does not cancel backend work. Dismissing generic task records does not destroy feature-owned prune preview metadata/projections. Task commands invalidate task queries; browser-owned partial uploads also invalidate their actual immediate writes.

Finite restoration SSE remains request-owned and is cancelled when its view closes. It is distinct from independent background tasks even when both display progress.

## Client state

- `panelStore.ts`: panel open state, active tab and drag position. Only the launcher position persists.
- `downloadStore.ts`: browser download records and live AbortControllers. Persisted in-flight records become cancelled on reload because an HTTP download cannot resume from a serialized controller.
- `downloads.ts`: public download command adapter; archives and ordinary files supply the HTTP operation and progress callback.

`ui/TaskCenterTrigger.tsx`, `TaskCenterPanel.tsx`, `BackgroundTaskList.tsx`, `BackgroundTaskItem.tsx`, `DownloadTaskList.tsx` and `DownloadTaskItem.tsx` present these states. The public `ui/index.ts` entry is used by the app shell.
