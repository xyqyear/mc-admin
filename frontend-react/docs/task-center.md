# Task Center

The globally mounted task center displays backend tasks and browser downloads across page navigation. `features/tasks/` owns task DTOs, transport, polling, commands, downloads and UI. `app/layout/MainLayout.tsx` mounts its public trigger/panel.

## Backend task state

`contracts.ts` contains the HTTP DTO and the camel-case view model; `api.ts` performs that explicit conversion. Backend statuses are lowercase `pending`, `running`, `completed`, `failed`, `cancelled`. Dynamic result objects remain feature-validated where a workflow consumes them.

TanStack Query is the only backend-task state owner. `queries.ts` owns `taskQueryKeys`, list/active/detail requests and polling. Lists and the badge poll every second while active tasks exist, otherwise every ten seconds; task details poll every two seconds until terminal. The badge reads the active-task query directly. There is no background-task Zustand mirror.

Task items render progress/message/result/error, allow explicit cancellation when a pending/running task is cancellable, and allow terminal records to be dismissed. The panel shows active tasks and terminal results from the last thirty minutes (records without an end time remain visible); clearing completed records sends the existing task API command.

Manual snapshot creation and file/world restore/rollback, lifecycle, creation/synchronization, file/archive deletion, map initialization, manual self-check/DNS and upload hashing/publication return `202 {task_id}`. `commands.ts` exports `waitForTaskResult` for their initiating workflows: it observes task detail every second, updates Query cache, keeps waiting through transient read failures with a reconnect notice, and invokes terminal handlers only after a confirmed outcome. Dismissing a task does not remove its retained detail or result. A 404 ends observation with a missing/expired-record message and asks the user to refresh the relevant page to check the actual outcome. An AbortSignal detaches the observer; it does not cancel the task. Authentication expiry stops observation. Task acceptance and 100% progress alone never unblock a workflow.

Server controls show the maintenance reason and a task link when available. Creation, map initialization, self-check, DNS and synchronization also discover active work when reopened. Map initialization retains its non-dismissible progress dialog; existing file/upload forms retain their original busy state and terminal behavior. Browser File objects are not persisted by the task center. `openTaskCenter` opens the background tab without giving feature components ownership of panel state.

## Completion ownership

`app/operations/OperationObserver.tsx` owns business-cache completion effects through feature resource registries for configuration, servers, files/archives, world, backups/history, health and DNS. Configuration, populate/compression/ownership presentation and world restore/prune views display outcomes without owning those effects. Closing independent-task dialogs does not cancel backend work. Dismissing generic task records does not destroy feature-owned prune preview metadata/projections. Task commands invalidate task and operation discovery; browser-owned partial uploads also invalidate their actual immediate writes.

File and world recovery share independent tasks. Their progress dialogs retain the existing closing restrictions until the confirmed terminal state, including across failed reads. Database-only active restoration discovery resumes observation after navigation or reload; terminal results remain visible until dismissed. Disconnecting observation never cancels the writer. Explicit task cancellation waits for writer termination and cleanup before reporting its result.

## Client state

- `panelStore.ts`: panel open state, active tab and drag position. Only the launcher position persists.
- `downloadStore.ts`: browser download records and live AbortControllers. Directory batches retain aggregate bytes, discovered/saved/failed file counts, destination and bounded failure/name-mapping details. Persisted in-flight records become cancelled on reload because an HTTP download cannot resume from a serialized controller.
- `downloads.ts`: public download command adapter; archives and ordinary files supply the HTTP operation and progress callback. Browser-owned directory export supplies a streaming executor and aggregate progress through `executeManagedDownload`.

`features/files/useDirectoryDownload.ts` invokes the writable directory picker during the initiating click, before asynchronous requests. Its executor reads bounded recursive manifest pages, binds content reads to the manifest's server generation and writes response streams into a separate local export folder with four concurrent transfers. Original layouts retain empty directories and use the captured browsing/search root. Flat layouts retain files, resolving duplicates, case-insensitive collisions and unsupported local names without overwriting existing files; task details display adjusted names. A file becomes complete only after its writable stream closes. Failed or cancelled transfers remove incomplete output while successful files remain. Closing the initiating view or task panel does not stop execution; cancellation aborts active reads and prevents later transfers, and refresh/closure ends the browser-owned work. Direct export reads live server files rather than a point-in-time snapshot.

`ui/TaskCenterTrigger.tsx`, `TaskCenterPanel.tsx`, `BackgroundTaskList.tsx`, `BackgroundTaskItem.tsx`, `DownloadTaskList.tsx` and `DownloadTaskItem.tsx` present these states. The public `ui/index.ts` entry is used by the app shell.
