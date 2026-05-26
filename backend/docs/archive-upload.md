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

After SHA256 verification succeeds, the backend copies the temp file into a hidden staging file inside the archive directory, atomically replaces the final archive path from that staging file, applies archive-directory ownership to the final file, and removes the `/tmp` upload part.

The staging step keeps the final archive path from exposing a partial file even when `/tmp` and the archive directory are on different filesystems.

## Offset Rules

The server-side temp file size is authoritative. A `PATCH` whose `Upload-Offset` does not match the current size returns `409` with the current offset so the frontend can resume from the server's view.

## SHA256

`GET /archive/upload/{upload_id}/sha256/stream` streams Server-Sent Events:

- `start` — file size and filename.
- `progress` — bytes read and percentage.
- `complete` — final hex SHA256.

The frontend computes the local file hash at the same time. It then calls `POST /archive/upload/{upload_id}/verify` with the local SHA256. If the hashes match, the backend publishes the archive. If they differ, the backend deletes the temp upload and removes the session.
