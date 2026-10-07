## Why

Issue #175 asks administrators to inspect online players without leaving the server overview and operate on selected files together. Search results and folders need the same download and recovery capabilities as the ordinary file list, with meaningful snapshot notes.

## What Changes

- Open the existing player detail dialog from the server overview in place.
- Share path-based batch selection and snapshot creation/recovery, compression and deletion between the file list and advanced search; search-folder groups aggregate only their actual matching entries.
- Save selected files and recursive folders directly into a user-authorized local directory on capable browsers, with flat or original-path layouts and retained packing controls.
- Keep direct-download controls visible when unavailable, with Chinese capability/environment tooltips and no browser version text.
- Store editable snapshot notes without changing snapshot identity.
- Preserve existing task acceptance, safety snapshots, restoration history, exclusion protection and truthful partial outcomes.
- Share activity-aware restoration discovery across file, world and history consumers, preserving fresh admission checks while reducing idle polling and repeated repository reads.
- Place selected counts and batch controls below file lists and advanced-search results without empty-selection space, keeping file rows stable through selection, clearing and asynchronous checks.
- Name packed archives and local export folders with the server name and browser-local timestamp, without random identifiers or selected-path fragments, while preserving existing output on name collisions.
- Player-specific complete rollback and its research are outside this change.

## Capabilities

### New Capabilities
- `file-batch-operations`: stable selection, scoped batch commands, recursive directory downloads, layouts and browser capability feedback.

### Modified Capabilities
- `snapshot-recovery`: multi-path file/search entrypoints and persistent editable notes.
- `administration-compatibility`: in-place player detail access from the server overview.

## Impact

Backend files/archive APIs gain additive batch request contracts and a bounded recursive download listing. Snapshots gain note metadata endpoints and an additive database migration. Frontend files, players, backups and browser download tasks compose the existing concrete feature boundaries. Existing single-path API behavior remains supported. Docker dependencies and deployment topology do not change; frontend and backend deploy together. API E2E, browser journeys and directly affected unit/integration tests cover the new behavior.
