# Archive Uploads (`app.archive.uploads`)

Archive uploads use a short-lived resumable protocol instead of multipart form uploads. The frontend creates an upload session, appends raw byte chunks, then verifies the completed archive with SHA256.

## Protocol

1. `POST /archive/upload/init` creates a session from `path`, `filename`, `size`, and `allow_overwrite`.
2. `HEAD /archive/upload/{upload_id}` returns the server offset in `Upload-Offset`.
3. `PATCH /archive/upload/{upload_id}` appends one raw `application/octet-stream` chunk at the required `Upload-Offset`.
4. `GET /archive/upload/{upload_id}/sha256/stream` hashes the completed temp upload as SSE.
5. `POST /archive/upload/{upload_id}/verify` compares the client SHA256 with the server SHA256 and publishes the archive on match.
6. `DELETE /archive/upload/{upload_id}` cancels the session and removes the temporary file.

Chunks are 8 MiB. Sessions expire after 60 minutes of inactivity and live only in memory. Temporary upload files live under `/tmp/mc-admin-archive-uploads/`.

## Finalization

When the received byte count reaches the declared file size, the session enters pending verification and the `/tmp` upload part remains the only copy of the uploaded bytes. The final archive path is not created yet.

After SHA256 verification succeeds, the backend copies the temp file into a hidden staging file inside the archive directory and applies archive-directory ownership. Overwrite mode atomically replaces the final path. No-overwrite mode atomically links the staging inode to a previously absent destination, returning 409 if another writer has occupied it, then unlinks the staging name. Both modes remove the `/tmp` upload part after publication.

The staging step keeps the final archive path from exposing a partial file even when `/tmp` and the archive directory are on different filesystems.

Publication owns target and staging paths through `ARCHIVE` claims. Archive
create/delete/rename and population use the same namespace; a busy overlapping
mutation returns 423. Upload verification waits for an overlapping publication
to finish, then checks the destination again. Concurrent no-overwrite uploads
to the same filename therefore return one success and one 409; the conflicting
session retains its verified temporary bytes for retry or cancellation.
Chunk-offset mismatch retains its structured 409.
The finite chunk append and its session-state update finish under the session
lock despite request cancellation. Verification finishes session cleanup after
publication. Explicit cancellation before verification removes the pending upload.

## Offset Rules

The server-side temp file size is authoritative. A `PATCH` whose `Upload-Offset` does not match the current size returns `409` with the current offset so the frontend can resume from the server's view.

## SHA256

`GET /archive/upload/{upload_id}/sha256/stream` streams Server-Sent Events:

- `start` — file size and filename.
- `progress` — bytes read and percentage.
- `complete` — final hex SHA256.

The frontend computes the local file hash at the same time. It then calls `POST /archive/upload/{upload_id}/verify` with the local SHA256. If the hashes match, the backend publishes the archive. If they differ, the backend deletes the temp upload and removes the session.

## Compression output identity

Each compression task receives a filename containing the readable server/path, timestamp, and a random identifier. Independent tasks never intentionally share an output path; failure and cancellation remove only that task's partial archive. Closing the progress dialog leaves the background task running.

`app.archive.application` plans source file scope and output before task
acceptance. Compression reads under its server file lease and writes an owned
`.mc-admin-archive-<token>.tmp` on the destination filesystem. After compression
and adapter cleanup succeed, it atomically replaces the final path and publishes
completion. Listings omit this reserved staging namespace. The compression utility
is the CLI adapter; resource ownership and publication belong to the application.

The journal retains the exact archive-relative stage path and token. Normal
finalization removes only that stage. Startup retries unresolved stages, including
failed terminal records, after verifying writers stopped. Cleanup rejects
redirected parents and never scans by prefix. Unknown writers retain their
artifact and block its archive paths, without freezing unrelated server files.
Population stages have equivalent ownership under the captured server generation.
Interrupted extraction and compression are never replayed automatically.
