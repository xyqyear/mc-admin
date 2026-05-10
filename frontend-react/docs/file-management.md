# Server File Management

Per-server file browser, editor, search, and upload UI. Reached from a server's overview at `/server/{id}/files`. Exposes everything the user might want to do to the server's data directory short of opening a shell.

## Layout

```
┌────────────────────────────────────────────────┐
│ FileBreadcrumb · FileToolbar (upload/create…)  │
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

## Single-file editing

`FileEditModal.tsx` opens a Monaco editor populated by `GET /files/content`. Auto-detects the language from the extension via `utils/fileLanguageDetector.ts`. **SNBT** (Minecraft NBT serialized as text) is registered as a custom Monaco language in `main.tsx`; editing one of these is the same as editing YAML/JSON, just with the right tokenizer.

`FileDiffModal.tsx` shows a Monaco diff editor — used when an external change collides with a pending edit.

## Multi-file upload

Folder drag-drop generates many files at once with potential conflicts. `MultiFileUploadModal.tsx` runs the session-based flow:

1. **Manifest** — frontend collects `{path, size}` for every dropped item, builds `FileUploadTree.tsx`.
2. **Conflict check** — POST manifest → backend returns `session_id` + conflict list.
3. **Conflict resolution** — `ConflictTree.tsx` displays conflicts; user picks an `OverwritePolicy` (`always_overwrite`, `never_overwrite`, or per-file decisions).
4. **Policy submit** — POST to `/upload/session/{id}/policy`.
5. **Blob upload** — files posted; backend writes per the stored decisions.

The intermediate `FileUploadTree` mirrors the resolved decisions so the user can see exactly what's about to happen before the bytes go up.

`hooks/usePageDragUpload.ts` is the page-level drop-zone hook — validates dropped items (no system files, no overly large directories), then pipes into the modal flow.

## Deep search

`FileDeepSearchModal.tsx` runs against `GET /files/search`:

- Regex (toggle) or substring
- Case sensitivity toggle
- Subfolder recursion toggle (max-depth knob)
- Min/max file size
- Newer-than / older-than timestamps

Results render as a tree (`FileSearchResultTree.tsx`) with `HighlightedFileName.tsx` showing the match against the query. Clicking a result navigates the main browser to that path.

## Compression / decompression

Compressing a folder is a long operation; both happen as background tasks.

- `CompressionConfirmModal.tsx` → `submit /api/archives/...` returns a `task_id`
- `CompressionResultModal.tsx` watches the task via `useTask(task_id)`, shows progress, and surfaces the result archive when done

The user can navigate away — the task center continues to track the task and toasts on completion.

## Files

- `pages/server/servers/ServerFiles.tsx` — page shell
- `components/server/FileBreadcrumb.tsx`, `FileTable.tsx`, `FileToolbar.tsx`, `FileSearchBox.tsx`, `FileSearchResultTree.tsx`, `HighlightedFileName.tsx`, `DragDropOverlay.tsx`
- `components/modals/ServerFiles/MultiFileUploadModal.tsx`, `FileUploadTree.tsx`, `ConflictTree.tsx`, `CreateModal.tsx`, `RenameModal.tsx`, `FileEditModal.tsx`, `FileDiffModal.tsx`, `FileDeepSearchModal.tsx`, `CompressionConfirmModal.tsx`, `CompressionResultModal.tsx`
- `hooks/api/fileApi.ts`, `hooks/queries/base/useFileQueries.ts`, `hooks/mutations/useFileMutations.ts`
- `hooks/usePageDragUpload.ts`
- `utils/fileLanguageDetector.ts`, `utils/fileSearchUtils.ts`
