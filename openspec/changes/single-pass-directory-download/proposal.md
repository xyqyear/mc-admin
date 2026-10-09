## Why

Directory downloads alternate manifest pages with transfers, so discovered totals grow and progress moves backwards. A complete in-memory manifest establishes fixed byte totals and removes pagination overhead.

## What Changes

- **BREAKING**: Download manifests return all selected entries in one response; cursor and page-limit fields are removed.
- Scan selected roots once with Python and retain metadata only for the response.
- Start browser transfers after scanning, using one bounded queue and fixed byte progress.
- Preserve path layouts, empty directories, authenticated generation-bound transfers and partial failure/cancellation behavior.
- No temporary manifests, persistent jobs, fd integration or production-server changes.

## Capabilities

### New Capabilities

- `file-directory-download`: Complete selected manifests and browser directory exports with fixed byte progress.

### Modified Capabilities

None.

## Impact

Backend file DTOs, recursive filesystem scanning, frontend directory export/task presentation, API and browser coverage, and file-operation documentation. No database migration, dependency or Docker change.
