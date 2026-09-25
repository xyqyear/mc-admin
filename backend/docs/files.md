# File Operations (`app.files`)

CRUD for files inside a server's data directory, deep search, ownership repair, and multi-file upload with conflict resolution.

## Directory boundary and operation policies

Paths are confined to the managed data directory after resolving symlinks. External-target symlinks are rejected, including rename and deletion requests; internal symlink renames operate on the link itself. This is a directory boundary check, not a race-proof filesystem sandbox against concurrent symlink replacement.

Create and rename names are nonempty basenames other than `.` or `..`; `/` is a separator, while a backslash remains a literal Linux filename character. Root-directory deletion and renaming are rejected because server lifecycle operations own the data root. Multipart destination paths are all validated before any part is written or a single-use session is consumed; an invalid path rejects the request. Valid batches retain per-file overwrite and failure results and are not transactional for filesystem errors during writing.

Directory listings omit individual entries that disappear, become unreadable, or are broken symlinks. Other entries remain available; metadata and type are derived from the same stat result.

## Application ownership

`FileApplication` owns server file mutations. It resolves both lexical paths
and canonical targets into project-relative `FILES` claims, then rechecks those
claims after acquisition. Rename reserves its source and destination; directory
operations reserve the subtree. An internal symlink alias therefore conflicts
with a write to its actual target. The journal captures server generation and
resource scope, never file contents.

World maintenance reserves its affected file paths through the same coordinator.
Overlapping edits, deletes, renames and upload batches return 423 before writing.
Unrelated configuration/plugin files remain editable while the server runs or a
different world scope is maintained. Listing, content reads, search and downloads
do not acquire write leases. A global restore owns the global file root, including
names not registered when planning began; creation and explicit adoption cannot
enter that scope while it is occupied.

Uploads validate the whole batch before consuming its session, then reserve its
actual destinations. Rejected conflicts leave the session available for retry.
Cancellation waits for the current file write to finish and stops later files;
completed files remain. Finite filesystem cleanup finishes before lease release.
Large batches use a bounded journal summary while execution leases retain the
individual paths. Interrupted writes do not imply automatic rollback.

Ownership repair reserves the complete data tree until the owned `chown` process
and cleanup finish. Population atomically reserves maintenance, the data tree,
its unique stage and its input archive. Its worker rechecks paths and the
stopped/created status before extraction, excluding concurrent startup. Successful
population retains archive-consumption behavior. Failure may leave partial data;
only its owned stage is cleaned, after writers are confirmed stopped. Unknown
writers retain the stage and recovery evidence.

## Why a session-based upload flow

Drag-dropping a folder hits the API with potentially thousands of files, many of which may already exist. Forcing the user to confirm each conflict mid-upload is awful UX; pre-bundling the whole upload into one server-side decision is also awful (huge memory + an opaque "what just changed?" result). The session pattern is the middle path:

1. **Upload session opens** — frontend POSTs the file *manifest* (paths + sizes), backend returns a `session_id` and the list of conflicting paths.
2. **Frontend resolves conflicts** — the `MultiFileUploadDialog` shows the conflict tree; user picks an `OverwritePolicy` (`always_overwrite`, `never_overwrite`, or per-file decisions).
3. **Frontend submits policy** — `set_upload_policy(session_id, decisions)`.
4. **Frontend posts file blobs** — backend writes per the stored decisions and returns final results.

Sessions live in an in-memory dict (`_upload_sessions`) with a TTL; after expiry, an unfinished session is GC'd. The frontend sends at most 1000 files per request, sequentially; uploads spanning multiple requests use `reusable=true`. Cancellation stops further requests and preserves files already written.

## Modules

- `base.py` — file CRUD helpers: `get_file_items`, `get_file_content`, `update_file_content`, plus rename/delete via the `types` helpers.
- `application.py` — owned file commands and background ownership-repair execution.
- `resources.py` — canonical and lexical claims and acquisition-time revalidation.
- `population.py` — immutable population plan, stopped-state check and owned extraction stage.
- `paths.py` — shared HTTP path boundary: resolves symlinks before checking containment, returns 400 on escape, and validates create/rename basenames. Server file operations and archive download/compression/population use the same boundary; multipart validates every destination before writing any part.
- `multi_file.py` — session orchestrator: `check_upload_conflicts`, `set_upload_policy`, `upload_multiple_files`.
- `search.py` — `search_files` shells out to `fd` for fast regex search; filters cover regex, case sensitivity, max depth, min/max size, newer-than / older-than dates. Result rows are parsed from `stat` output into `SearchFileItem`.
- `types.py` — `FileItem`, `FileContent`, `MultiFileUploadRequest`, `FileStructureItem`, `OverwritePolicy`, `UploadSession`, plus the result models.
- `ownership.py` — background-task generator that runs `chown -R` against a server data tree using the data-root UID/GID.
- `utils.py` — session create/get/remove helpers; TTL enforcement; ownership helpers for new files and directories.

## Why `fd` for deep search

Deep search runs against trees with potentially hundreds of thousands of files (modpack assets, region files). Python's `os.walk` + per-file regex is slow; `fd` is Rust-backed, multi-threaded, and respects `.gitignore`/path filters out of the box. We pre-validate the search root sits inside the server's data dir (no traversal) before invocation, then parse stdout into typed rows.

## SNBT

The frontend's Monaco editor opens NBT data files as SNBT (string NBT). The backend doesn't parse SNBT — it just round-trips the file content. Editing happens entirely client-side; the user submits a new SNBT string, the backend writes it back.

`tests/files/test_application_ownership.py` uses independent temporary SQLite and
filesystem state, execution barriers and real Restic/7z adapters to verify scope,
online operations, cancellation, publication and recovery.
