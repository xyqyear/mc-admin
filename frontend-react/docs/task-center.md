# Task Center

Floating panel that surfaces every long-running operation in one place — backend background tasks (compression, populate, rebuild, world-restore staging) and browser-side downloads (archive download with progress). The panel is mounted globally so a task started on one page can be monitored after navigating elsewhere.

## Why one panel for two task kinds

"Server compression" and "archive download" feel different — one runs on the backend, one in the browser — but from the user's standpoint they're the same: "something is running, show me progress, let me cancel". A single floating UI with two tabs ("后台任务" / "下载") and one badge count covers both, and removes a class of bugs where users lose track of in-flight work after navigating.

## Components

- `TaskCenterTrigger.tsx` — fixed-position button with a badge for active task count. Mounted at app root in `MainLayout` so every page can see it.
- `TaskCenterPanel.tsx` — `<Card>` with `<Tabs>` (background tasks + downloads). Open/close + active-tab state lives in `useTaskCenterStore`.
- `BackgroundTaskList.tsx` / `BackgroundTaskItem.tsx` — backend task list. Polls `useBackgroundTasks` (1 s when at least one task is active, 10 s otherwise — the polling cadence flips automatically based on the result set).
- `DownloadTaskList.tsx` / `DownloadTaskItem.tsx` — browser download list, sourced from `useDownloadStore` (Zustand, persisted to localStorage so a refresh doesn't lose progress).

## Backend task lifecycle

Each task arrives from `/api/tasks/` with a status (`PENDING / RUNNING / COMPLETED / FAILED / CANCELLED`), `progress` (0–100 or null), `message`, and an optional `result`. The item renders:

- A progress bar (indeterminate when `progress` is null)
- The status message
- A `<Popover>` with `result` JSON if present (so users can inspect what changed)
- A cancel button (gated on `cancellable && status === RUNNING`)

When a task completes, the item stays in the list until the user clicks dismiss, or `clear all completed` runs. Completion also fires a Sonner toast — useful for long compressions where the user has tabbed away.

## Auto-completion + cache invalidation

The progress modal that *initiates* a task (e.g. `RebuildProgressModal`) owns the post-completion cache invalidation, not the task center. The task center is a passive viewer — it never invalidates business queries, only `taskQueryKeys`. This keeps invalidation logic close to the operation that triggered it.

## Stores

- `useTaskCenterStore` — `{ open: boolean, activeTab: 'background' | 'downloads' }`. Not persisted; resets on reload.
- `useBackgroundTaskStore` — mirrors backend task list locally for the badge count + offline rendering.
- `useDownloadStore` — pure-client downloads, persisted to localStorage so an in-progress download survives a refresh.

## Files

- `components/task-center/TaskCenterTrigger.tsx`
- `components/task-center/TaskCenterPanel.tsx`
- `components/task-center/BackgroundTaskList.tsx`
- `components/task-center/BackgroundTaskItem.tsx`
- `components/task-center/DownloadTaskList.tsx`
- `components/task-center/DownloadTaskItem.tsx`
- `hooks/queries/base/useTaskQueries.ts`
- `hooks/mutations/useTaskMutations.ts`
- `stores/useTaskCenterStore.ts`, `useBackgroundTaskStore.ts`, `useDownloadStore.ts`
