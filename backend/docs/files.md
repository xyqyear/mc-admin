# File Operations (`app.files`)

CRUD for files inside a server's data directory, plus deep search and multi-file upload with conflict resolution.

## Why a session-based upload flow

Drag-dropping a folder hits the API with potentially thousands of files, many of which may already exist. Forcing the user to confirm each conflict mid-upload is awful UX; pre-bundling the whole upload into one server-side decision is also awful (huge memory + an opaque "what just changed?" result). The session pattern is the middle path:

1. **Upload session opens** — frontend POSTs the file *manifest* (paths + sizes), backend returns a `session_id` and the list of conflicting paths.
2. **Frontend resolves conflicts** — the `MultiFileUploadDialog` shows the conflict tree; user picks an `OverwritePolicy` (`always_overwrite`, `never_overwrite`, or per-file decisions).
3. **Frontend submits policy** — `set_upload_policy(session_id, decisions)`.
4. **Frontend posts file blobs** — backend writes per the stored decisions and returns final results.

Sessions live in an in-memory dict (`_upload_sessions`) with a TTL; after expiry, an unfinished session is GC'd.

## Modules

- `base.py` — file CRUD helpers: `get_file_items`, `get_file_content`, `update_file_content`, `upload_file`, plus rename/delete via the `types` helpers. `upload_file` is used by archive uploads; server file uploads use the session flow.
- `multi_file.py` — session orchestrator: `check_upload_conflicts`, `set_upload_policy`, `upload_multiple_files`.
- `search.py` — `search_files` shells out to `fd` for fast regex search; filters cover regex, case sensitivity, max depth, min/max size, newer-than / older-than dates. Result rows are parsed from `stat` output into `SearchFileItem`.
- `types.py` — `FileItem`, `FileContent`, `MultiFileUploadRequest`, `FileStructureItem`, `OverwritePolicy`, `UploadSession`, plus the result models.
- `utils.py` — session create/get/remove helpers; TTL enforcement.

## Why `fd` for deep search

Deep search runs against trees with potentially hundreds of thousands of files (modpack assets, region files). Python's `os.walk` + per-file regex is slow; `fd` is Rust-backed, multi-threaded, and respects `.gitignore`/path filters out of the box. We pre-validate the search root sits inside the server's data dir (no traversal) before invocation, then parse stdout into typed rows.

## SNBT

The frontend's Monaco editor opens NBT data files as SNBT (string NBT). The backend doesn't parse SNBT — it just round-trips the file content. Editing happens entirely client-side; the user submits a new SNBT string, the backend writes it back.
