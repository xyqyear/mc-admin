## Purpose

Let administrators operate on precisely selected server files from both directory browsing and advanced search, and export their contents into authorized local folders or persistent packed archives with truthful results.

## ADDED Requirements

### Requirement: Selection identifies actual targets
The system SHALL identify selected entries by their complete server data-relative paths. Sorting and pagination SHALL preserve selection. A changed server, directory or executed search SHALL reset selection. Synthetic search-tree ancestors SHALL NOT become recursive operation targets. Requests SHALL freeze their selected scope when confirmed.

#### Scenario: Search grouping does not expand an operation
- **WHEN** search results contain files under a synthetic parent that was not itself matched
- **THEN** only real selected matches are submitted and unrelated siblings remain untouched

#### Scenario: Pagination preserves identity
- **WHEN** a user selects same-named files on different pages and sorts the list
- **THEN** both original paths remain selected and page selection only changes that page

### Requirement: Batch file commands preserve scoped outcomes
The system SHALL support snapshot creation, snapshot recovery, direct download, compression and deletion for selected file-list and advanced-search entries. Batch deletion SHALL validate the complete scope before writing, reject root deletion and path escapes, reserve all affected resources and report per-target results. Execution failures SHALL NOT claim transactional rollback. Compression SHALL produce one archive retaining data-relative paths, disjoint parent scopes and empty directories.

#### Scenario: Invalid deletion target rejects the batch
- **WHEN** an authenticated deletion batch includes a valid file and an escaping or root target
- **THEN** no member is deleted and no successful task is reported

#### Scenario: Partial execution is visible
- **WHEN** a target cannot be deleted after another target was deleted
- **THEN** results identify deleted and failed targets and preserve failed selection for retry

#### Scenario: Same-named archive entries remain independent
- **WHEN** selected files in two directories have the same basename
- **THEN** both contents appear under their original paths in the completed archive

### Requirement: Local folder export is capability-aware and bounded
The system SHALL offer direct export of selected files and recursive real folders to a user-selected writable local directory on capable secure browsers. Direct-download controls SHALL remain visible when unavailable, with a hover reason naming Chrome and Edge without versions for browser incompatibility and a separate secure-context reason. Packing SHALL remain independently available. Downloads SHALL stream content with bounded concurrency and preserve successfully completed files on cancellation. Browser refresh or closure SHALL NOT be presented as continued server-owned execution.

#### Scenario: Authorized directory export
- **WHEN** a capable user selects a writable local directory and starts a recursive download
- **THEN** the export creates a separate destination folder, reports aggregate bytes/files, and counts a file complete only after writing finishes

#### Scenario: Unsupported browser feedback
- **WHEN** the browser lacks direct directory export support
- **THEN** the visible disabled control exposes a Chinese hover explanation naming Chrome and Edge without browser versions

#### Scenario: Cancellation preserves completed output
- **WHEN** a user cancels a batch with completed and pending files
- **THEN** active transfers stop, pending files do not start, and already completed files remain

### Requirement: Export layout is explicit and collision-safe
Advanced search SHALL offer flat and original-path layouts. Original paths SHALL be relative to the captured search root; directory browsing SHALL use the captured browsing directory. Flat names, local filename restrictions and case-insensitive collisions SHALL NOT silently overwrite another selected or existing file. Synthetic grouping directories SHALL NOT expand the export.

#### Scenario: Flat collision is resolved explicitly
- **WHEN** two selected files share a basename in flat mode
- **THEN** both files receive distinct output names with preserved content and visible mapping feedback

#### Scenario: Original-path layout
- **WHEN** selected matches below a non-root search directory are exported with original paths
- **THEN** their hierarchy is relative to that captured root regardless of later navigation

### Requirement: Batch controls preserve list geometry
The file browser and advanced-search results SHALL retain stable batch-control space across selection changes and asynchronous snapshot eligibility checks. Checking, rejected and partially ignored scope explanations SHALL be available from the snapshot action controls without adding or removing a flow row above or below the file list.

#### Scenario: Eligibility response does not move selectable rows
- **WHEN** a selected scope changes from checking to allowed or ignored
- **THEN** snapshot controls reflect the current eligibility and explain it on hover while selectable rows and the batch-control area retain their positions

#### Scenario: Selection does not insert a new control row
- **WHEN** an administrator selects the first result or clears the last selection
- **THEN** batch controls become available or hidden inside their retained layout area without displacing the file list

### Requirement: Export names use the server and browser-local time
Packed archives and local export folders created through the browser SHALL use the filesystem-safe server name and a browser-local timestamp, without hashes, random identifiers or selected-path fragments. Archive names SHALL retain their format extension. Existing outputs SHALL remain intact on collisions; a numeric collision suffix MAY distinguish an additional output. Legacy archive requests without a client timestamp SHALL remain supported.

#### Scenario: Browser timezone differs from the server
- **WHEN** an administrator creates an archive or exports a local folder with a browser timezone different from the backend timezone
- **THEN** the final name reflects the browser-local calendar date and clock time rather than a UTC ISO string or the backend clock

#### Scenario: Repeated timestamp preserves earlier output
- **WHEN** another export uses the same server name and timestamp as an existing output
- **THEN** the new output receives a distinct name and the earlier output retains its original content
