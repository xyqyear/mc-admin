# Archive Upload Dialog

`ArchiveUploadDialog` renders the local `hooks/uploads/useArchiveUpload.ts` flow: selecting `.zip` / `.7z` files, sending resumable chunks, pausing/resuming the active upload, and verifying SHA256 after upload.

## Upload Flow

The flow hook calls the raw archive API layer directly because upload progress belongs to the dialog lifetime. It owns the fixed file queue, active session, current request, and retry timers. Files and chunks run sequentially; additional page drops cannot replace an active or paused queue. Pause aborts the current request; resume waits for its settlement before reading the authoritative server offset. Closing or unmounting aborts the run, clears retry timers, and cancels a known unfinished session. Late callbacks cannot update or resume a replacement run. Browser refresh does not persist upload state.

1. `initArchiveUpload` creates a backend upload session.
2. `uploadArchiveChunk` sends 8 MiB `Blob` slices with the current `Upload-Offset`.
3. `getArchiveUploadStatus` reads the server offset when resuming or recovering from a `409` offset mismatch.
4. `verifyArchiveUpload` publishes the archive only after SHA256 verification succeeds.
5. `cancelArchiveUpload` is called when the flow closes or unmounts with an unfinished active session.

The backend's offset is authoritative. Retryable upload requests use exponential backoff starting at 1 second and capped at 10 seconds, then keep retrying until the request succeeds, the user pauses, or the backend reports that the upload session no longer exists. The retry state shows a countdown and an immediate retry action.

If a retry eventually reaches the backend after the short-lived upload session has expired, the dialog moves into an error state, discards the active session, and lets the user choose an archive again, start a fresh upload, or close the dialog.

Clicking outside the dialog only closes it before an upload starts. Uploading, retrying, paused, failed, verifying, and completed states require an explicit button action.

## Verification Flow

After the upload completes, the dialog calculates SHA256 from both sides:

- Local hash: `hash-wasm` incremental SHA256 over file slices.
- Server hash: `GET /archive/upload/{upload_id}/sha256/stream` consumed through `readEventStream`.

The progress bar is reused for verification by averaging local and server hash percentages. After both hashes are available, the dialog calls `verifyArchiveUpload` with the local SHA256. The backend publishes the archive only on match. A local/server mismatch cancels the pending session; the backend also rejects and cleans up a mismatched verify request. The archive list is invalidated only after publish succeeds.

## SSE

`utils/eventStream.ts` contains the authenticated fetch-based SSE reader and parser. `hooks/useEventStream.ts` wraps that reader for state-driven component use. Imperative flows such as archive SHA256 verification use `readEventStream` directly.
