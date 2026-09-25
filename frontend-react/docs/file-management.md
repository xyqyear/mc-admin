# Server File Management

Per-server file browser, editor, search, upload, and ownership-repair UI. Reached from a server's overview at `/server/{id}/files`. Exposes everything the user might want to do to the server's data directory short of opening a shell.

## Layout

```
┌────────────────────────────────────────────────┐
│ FileBreadcrumb · FileToolbar                  │
│ (upload/create/repair…)                       │
├────────────────────────────────────────────────┤
│ FileSearchBox (basic in-folder)                │
├────────────────────────────────────────────────┤
│                                                │
│  FileTable (current directory)                 │
│  └ row click → navigate into folder /          │
│    open file in editor                         │
│                                                │
└────────────────────────────────────────────────┘
```

URL is the source of truth: `?path=<dir>&q=<query>&regex=<bool>`. Reload preserves location and search state.

Game-port self-check remediation links to `/server/<encoded-server-id>/files?path=%2F&q=server.properties&regex=false`. `/` is the server data root. The search input and results follow URL changes, including browser back/forward; literal search keeps the dot from acting as a regex wildcard. Users open the file through the normal editor, which retains its Compose-override reminder. The route uses the existing session guard and server/file error handling.

## Ownership repair

`FileToolbar.tsx` exposes a confirmed "修复文件所有权" action at the top of the file manager. The mutation calls `POST /servers/{id}/files/ownership/restore`, receives a `task_id`, and `useFileBrowser` polls that task with `useTask(task_id)`. The backend task recursively sets every file in the server data directory to the UID/GID of that directory; the application operation observer invalidates the file-list cache after terminal outcomes, including partial failures. The task is also visible in the global task center.

## Single-file editing

`FileEditDialog.tsx` opens a Monaco editor populated by `GET /files/content`. Auto-detects the language from the extension via `features/files/languageDetection.ts`. **SNBT** (Minecraft NBT serialized as text) is registered as a custom Monaco language in `main.tsx`; editing one of these is the same as editing YAML/JSON, just with the right tokenizer.

The dialog waits for successfully loaded content before enabling edits or save. An empty successful response is a valid baseline; users can intentionally save empty content. Failed initial reads show a retry action. A failed save keeps the dialog and authored draft, and a later background read does not overwrite those edits. Saving disables editing and dismissal until the write settles; the dialog closes on success. Ordinary online file editing uses the same flow.

`FileDiffDialog.tsx` compares the latest loaded server content with the local draft, including changes to or from an empty file. The comparison does not enforce a server-side version check.

## Multi-file upload

Folder drag-drop generates many files at once with potential conflicts. `MultiFileUploadDialog.tsx` displays `features/files/useMultiFileUpload.ts`, which owns the session-based flow:

1. **Manifest** — frontend collects `{path, size}` for every dropped item, builds `FileUploadTree.tsx`.
2. **Conflict check** — POST manifest → backend returns `session_id` + conflict list.
3. **Conflict resolution** — `ConflictTree.tsx` displays conflicts; user picks an `OverwritePolicy` (`always_overwrite`, `never_overwrite`, or per-file decisions).
4. **Policy submit** — POST to `/servers/{serverId}/files/upload/policy?session_id={id}&reusable={boolean}`.
5. **Blob upload** — files posted; backend writes per the stored decisions.

The flow fixes the file list when conflict checking starts and treats checking as busy. Its single batch-size constant decides both `reusable` and sequential batches of at most 1000 files; the raw API layer sends one batch. Closing, changing the target, or unmounting aborts the current request and ignores late callbacks. Cancellation preserves already-written files and invalidates the file listing; it does not roll back the batch.

The intermediate `FileUploadTree` mirrors the resolved decisions so the user can see exactly what's about to happen before the bytes go up.

`shared/hooks/usePageDragUpload.ts` is the page-level drop-zone hook — collects dropped files and nested directory entries, then passes them to the dialog flow.

## Deep search

`FileDeepSearchDialog.tsx` runs against `POST /servers/{serverId}/files/search`:

- Regex (toggle) or substring
- Case sensitivity toggle
- Subfolder recursion toggle
- Min/max file size
- Newer-than / older-than timestamps

Results render as a tree (`FileSearchResultTree.tsx`) with `HighlightedFileName.tsx` showing the match against the query. Clicking a result navigates the main browser to that path.

## Compression / decompression

Compressing a folder is a long operation; both happen as background tasks.

- `CompressionConfirmDialog.tsx` → `POST /api/archive/compress` returns a `task_id`
- `useFileBrowser` watches the task via `useTask(task_id)` and supplies progress to `CompressionConfirmDialog.tsx`; `CompressionResultDialog.tsx` presents the finished archive

The user can navigate away — the task center continues to track the task and toasts on completion.

## Files

- `pages/server/servers/ServerFiles.tsx` — route adapter; `features/files/FileBrowserScreen.tsx` — presentation
- `features/files/components/FileBreadcrumb.tsx`, `FileTable.tsx`, `FileToolbar.tsx`, `FileSearchBox.tsx`, `FileSearchResultTree.tsx`, `HighlightedFileName.tsx`; shared `shared/components/DragDropOverlay.tsx`
- `features/files/components/dialogs/MultiFileUploadDialog.tsx`, `FileUploadTree.tsx`, `ConflictTree.tsx`, `CreateDialog.tsx`, `RenameDialog.tsx`, `FileEditDialog.tsx`, `FileDiffDialog.tsx`, `FileDeepSearchDialog.tsx`, `CompressionConfirmDialog.tsx`, `CompressionResultDialog.tsx`
- `features/files/api.ts`, `features/files/queries.ts`, `features/files/commands.ts`
- `shared/hooks/usePageDragUpload.ts`
- `features/files/languageDetection.ts`, `features/files/search.ts`

## Feature controllers and completion

`features/files/contracts.ts`, `api.ts`, `queries.ts` and `commands.ts` own the file protocol and server-state behavior. `useFileNavigation` preserves URL path/query/regex navigation and browser history. `useFileEditor` owns draft lifetime; `useFileBrowser` coordinates CRUD, confirmations, directory drag/drop and task presentation. The route and progress dialogs do not own independent task completion.

`operationResources.ts` registers file/archive/snapshot terminal effects with the app observer. Closing populate progress or leaving a compression/ownership view never cancels its backend task. A file restore is a finite request: `shared/operations/useRestoreRequest` latches snapshot/server/paths at confirmation, aborts on unmount, and distinguishes explicit completion from an incomplete stream. Browser-owned upload cancellation preserves earlier writes and refreshes affected directories even after unmount.

Real QueryClient/MSW tests exercise empty-file writes, a rejected online write with draft preservation, recursive regex/size/date filters, per-file overwrite policy, a reusable 1001-file upload cancelled during the second batch, and closing independent-task presentation.
