## Context

See `backend/docs/files.md` and `frontend-react/docs/file-operations.md`. The browser owns transfers and already tracks byte chunks, local output names, generation and cancellation.

## Goals / Non-Goals

Use one Python scan and one response, fixed frontend totals and one existing four-worker queue. Do not introduce fd, temporary manifests, database state, sessions or a new task abstraction.

## Decisions

- Replace the filesystem page walker with a single iterative `os.scandir` scan in a worker thread. Preserve path confinement, internal file links, unsupported directory-link reporting and per-entry errors; remove page cursors and directory stamps.
- Reuse the file-path request and retain entries, errors and generation in the response. The frontend sums sizes once; there is no duplicated backend total.
- Reuse `listingComplete` to distinguish scan from transfer. Only scanning uses indeterminate progress. Byte counts update while streams write; existing terminal task outcomes remain authoritative.
- Queue the complete manifest using the existing worker loop, retain local path mapping and output safety, and start the speed clock after scanning. Allow the scan request to finish without a client timeout while retaining explicit user cancellation.

## Risks / Trade-offs

The complete response and frontend metadata use memory proportional to entry count, as explicitly accepted. Files remain live; existing size validation and generation-bound GETs report changes during transfer. Scan requests remain finite HTTP reads with no retained backend job.

## Migration Plan

Backend and frontend ship together. Remove the obsolete page contract and its tests, update API/browser scenarios and current file documentation plus applicable AGENTS.md. No database migration or production changes are required; rollback uses the previous application image.
