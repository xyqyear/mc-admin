# File Operations (`app.files`)

CRUD for files inside a server's data directory, scoped batch deletion and compression, bounded download manifests, deep search, ownership repair, and multi-file upload with conflict resolution.

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
Unknown write failures produce a safe per-file reason and allow later members to
continue; bytes already written remain. Parent-directory or execution-time path
failures stop the batch with a safe string 500 response. Whole-batch preflight
keeps its 400/404 responses, and admission conflicts retain structured 423 errors.
Only explicitly authored safe operation messages are exposed; adapter exception
values and destination names are excluded from error logs.
Large batches use a bounded journal summary while execution leases retain the
individual paths. Interrupted writes do not imply automatic rollback.

`POST /servers/{server_id}/files/delete-batch` accepts `paths[]` and returns one
202 durable `file_delete` task. Every submitted member passes confinement,
existence and root-deletion checks before acceptance; overlapping lexical parent
targets are then consolidated. The worker reacquires all lexical and canonical
claims together and repeats the complete preflight before its first write.
One failed target does not stop unrelated later targets. Results retain each
effective target's `deleted`, `failed` or `pending` state, including safe failure
messages and counts. A partially failed task ends failed with its detailed result
still available. Cancellation waits for the current finite deletion and result
publication, then stops later targets. Already deleted files remain deleted;
pending targets have not started. The initial pending result is retained at
acceptance, including cancellation before execution. The existing single-path
DELETE interface remains supported.

## Browser-owned directory exports

`POST /servers/{server_id}/files/download-manifest` accepts frozen `paths[]`, an
optional opaque cursor and a page limit from 1 to 500 (default 200). Pages contain
data-relative file paths, byte sizes, directory paths including empty directories,
safe per-entry errors and `server_generation`. Selected parents subsume selected
children. There is no application-level total-file or selected-root count limit.
Enumeration retains a depth-first directory stack rather than the complete tree,
and closes all directory iterators when each page finishes. Continuing a page
reopens the current branch and skips its consumed directory entries; it does not
rescan unrelated completed subtrees. This avoids keeping a complete manifest or
per-file content in memory. Very large individual directories still incur offset
rescan cost across pages.

The cursor binds the registered server generation, data path and normalized
requested roots. Directory device/inode/mtime evidence rejects replaced or
structurally changed active branches with 409. Every request confines selected
roots again. Recursive enumeration never follows directory symlinks, including
internal aliases; it reports them as unsupported entries. Internal file links
are supported, while escaping or unreadable descendants produce safe errors.
Existing authenticated GET file downloads remain the transport; browser exports
pass `expected_generation` to reject same-name replacement servers. Legacy
download callers can omit that additive query parameter.

Direct export has no backend write lease or durable execution task. The browser
selects an authorized local folder, streams files with bounded concurrency and
owns flat/original path mapping, progress and cancellation. It is not a snapshot:
server files can change during enumeration or transfer. Size changes must be
reported by the browser; a page structure conflict requires starting a new
export. Browser refresh or closure ends transfers. Successfully completed local
files remain when later work fails or is cancelled.

## Scoped persistent compression

`POST /archive/compress` accepts either the existing `path`, omitted whole-project
scope, or additive `paths[]`; `path` and `paths` are mutually exclusive. A batch
archives disjoint data-relative roots into one 7z output, preserving original
paths, same-named files in separate directories and empty directories. Source
paths are confined and checked before accepting work and revalidated under the
execution lease. Literal include switches disable wildcard matching and avoid
interpreting `@` filenames as list files; archives store symlinks as links rather
than reading external target contents. Source argument batches remain below a
bounded byte budget, so large selections do not depend on a single command-line
argument limit. Each sequential addition writes the same private stage.

Archive names contain the filesystem-safe server name and `YYYYMMDD_HHmmss_SSS`
timestamp, without selected-path fragments or random identifiers. Browser commands
send the validated local calendar time through optional `client_timestamp`; legacy
API callers use the backend's local clock. Existing destinations receive numeric
suffixes such as ` (2)`. Internal stages keep independent ownership identifiers.

Compression reserves all sources, its independent output and its owned stage.
Only the completed stage is atomically published without replacing an existing
destination; a late collision fails while preserving the earlier archive.
Cancellation drains registered 7z processes and removes the owned partial stage
before releasing resources;
unknown writers retain their stage and recovery evidence. Packing remains
independent from direct directory export and uses the durable task center.

Ownership repair reserves the complete data tree until the owned `chown` process
and cleanup finish. Population atomically reserves maintenance, the data tree,
its unique stage and its input archive. Its worker rechecks paths and the
stopped/created status before extraction, excluding concurrent startup. Successful
population consumes the source archive after cleanup. Extraction and ownership
preparation finish in the stage before publication. Linux `renameat2` exchanges
the complete data directory with the prepared directory atomically; a missing
data directory uses rename. Both paths must share a filesystem supporting the
operation. Failure before publication preserves the original data and archive;
interruption across publication leaves either the old or complete new tree.
The exchanged old tree is cleaned with the owned stage after writers stop.
Cleanup failures report that the server files have already been replaced.
Unknown writers retain the stage and recovery evidence.

## Why a session-based upload flow

Drag-dropping a folder hits the API with potentially thousands of files, many of which may already exist. Forcing the user to confirm each conflict mid-upload is awful UX; pre-bundling the whole upload into one server-side decision is also awful (huge memory + an opaque "what just changed?" result). The session pattern is the middle path:

1. **Upload session opens** — frontend POSTs the file *manifest* (paths + sizes), backend returns a `session_id` and the list of conflicting paths.
2. **Frontend resolves conflicts** — the `MultiFileUploadDialog` shows the conflict tree; user picks an `OverwritePolicy` (`always_overwrite`, `never_overwrite`, or per-file decisions).
3. **Frontend submits policy** — `set_upload_policy(session_id, decisions)`.
4. **Frontend posts file blobs** — backend writes per the stored decisions and returns final results.

Sessions live in an in-memory dict (`_upload_sessions`) with a TTL; after expiry, an unfinished session is GC'd. The frontend sends at most 1000 files per request, sequentially; uploads spanning multiple requests use `reusable=true`. Cancellation stops further requests and preserves files already written.

## Modules

- `base.py` — file CRUD helpers: `get_file_items`, `get_file_content`, `update_file_content`, plus rename/delete via the `types` helpers.
- `application.py` — owned file commands, single/batch deletion and background ownership-repair execution.
- `downloads.py` — generation-bound recursive download pagination and opaque cursor validation.
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
