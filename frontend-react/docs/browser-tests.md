# Owned browser verification

`browser/` drives the built application in Chromium through real routes, Monaco, dialogs, HTTP, WebSockets and Leaflet. No business hook or QueryClient is replaced. `playwright.config.ts` uses one worker, no retries, and retains screenshots/traces for failed tests. The Go runner owns deployment, credentials, resource leases and cleanup; tests cannot attach to an arbitrary application.

The Chromium project uses `channel: 'chromium'` for the full browser's headless
mode. The default headless shell has an [upstream background-tab initialization
defect](https://github.com/microsoft/playwright/issues/42142) affecting native
middle/modifier clicks. New-tab checks still require actual pages, correct
destinations and preserved source state. Browser configuration participates in
the timing-history compatibility fingerprint.

## Local execution

Install Node 24 dependencies with `pnpm install --frozen-lockfile`, then `pnpm exec playwright install --with-deps chromium`. Local checks select only journeys directly related to the change and journeys affected through shared dependencies, with an explicit spec file and title filter. Complete project, component and browser test suites belong to GitHub Actions; do not reconstruct them locally through directory batches or subagents. Run from the frontend directory against the Docker config ID loaded from the release candidate OCI artifact:

```bash
BROWSER_OUTPUT_DIR=/tmp/browser-report \
  /path/to/mc-admin-e2e browser \
  --backend-image sha256:CANDIDATE_CONFIG_ID \
  --minecraft-image itzg/minecraft-server:java25-e2e-local-vanilla-1.21.11-64bb6d763bed \
  --output /tmp/browser-runs --run-id e2e-browser-unique \
  -- pnpm exec playwright test browser/journeys.spec.ts \
  --grep 'lifecycle acceptance stays blocked until task status confirms completion$'
```

This example selects the lifecycle acceptance journey; choose the explicit related titles for the actual change. Unfiltered `pnpm test:browser` is a full-suite CI command. Complete qualification uses the frozen case assignments described below. The complete GitHub Actions gates must pass for the latest commit SHA under `../AGENTS.md` and the [repository rules](../../AGENTS.md).

## Windows browser with a WSL-owned deployment

In the shared Windows checkout, install the browser with Windows pnpm:

```powershell
pnpm --dir frontend-react exec playwright install chromium
.\scripts\dev\e2e.ps1 build
.\scripts\dev\e2e.ps1 browser --backend-image mc-admin:dev --recipe server -- browser/navigation.spec.ts --grep 'EXACT_RELATED_TITLE$'
```

Choose the recipe required by the selected journey and replace the title filter
with explicit related titles. Build `mc-admin:dev` from the current source first.
The wrapper still requires `--backend-image`, a spec file and a title filter.
Windows Node/Playwright use the existing Windows `node_modules`; Linux does not
install or overwrite frontend dependencies.

The WSL Go runner creates the private fixture, deployment and cleanup journal.
Its child `scripts/dev/browser_bridge.py` launches PowerShell 7 and Windows
Node. A Windows Job Object owns the Playwright process tree; the child waits
for assignment before starting tests. Completion or loss of the WSL owner's
stdin closes the job and terminates its descendants before the bridge exits.
The original Go cleanup and result reporting then run normally.

`browser/host.ts` maps owned Linux paths through the selected distribution's
`\\wsl.localhost\DISTRIBUTION` share. It checks credential file permissions in
Linux and retains canonical runtime confinement checks. Docker subprocesses
and ownership changes execute in that same distribution. No fixture credentials
are copied into the checkout. Playwright reports default to the Windows
`frontend-react/test-results/browser` directory; deployment evidence remains in
the Linux E2E output directory described in [development](../../docs/development.md).

Native Linux CI uses the same fixture checks and direct host commands without
the Windows bridge. Browser transport and business assertions are shared.

## Fixture and evidence ownership

The wrapper writes a private `MC_ADMIN_BROWSER_FIXTURE` JSON containing the owned URL, credentials, server path and image/environment/manifest identities. Tests validate its local URL, directory ownership and private permissions. Never publish the runtime directory or private fixture. Publish the runner's redacted report/cleanup evidence and the Playwright results/report/artifacts; traces belong to short-lived test credentials and should still have restricted retention.

`MC_ADMIN_BROWSER_CLIENT_METADATA` optionally names a JSON file with `{path,url,version,sha1,size}` for an official Minecraft client. Tests verify the official download host, SHA1 and byte count before copying it into the owned server's map cache. Production palette generation and rendering still run normally. This fixture avoids repeated external downloads; it never supplies fabricated JARs, palettes or PNGs. Without it, the application downloads its normal dependency.

## Journey coverage

`monitoring.spec.ts` verifies one periodic monitoring source while sidebar and
overview are displayed, navigation to details, visible stale values during a
transport failure, and real stop/start with unavailable then renewed samples.
Fixture lifecycle commands wait for ready monitoring observations; the shared
response never substitutes for task settlement.

`release.spec.ts` compares deployed release JSON with selected source, then verifies upgrade notification and acknowledgment. It runs in complete browser qualification and metadata-only final-image checks with the same owned fixture and cleanup.

`task-progress.spec.ts` observes the built application's authenticated task SSE
headers and one shared connection. A verified owned Restic process remains paused
while the snapshot dialog keeps its close guard and receives no periodic task
detail reads. A controlled proxy then cuts SSE and this task's detail reads; the
backend completes the actual backup independently, and reconnecting restores the
authoritative result.
Public snapshot listing and source bytes verify the effect separately from UI
progress. The world recovery fault proxy cuts both SSE and detail observation
while a paused restore worker is still running with durable safety evidence;
the journey releases that writer, verifies completion, reconnects and rolls back.

The busy snapshot dialog can open a modal task center, inspect a completed task's
result through its popover, then return through both layers with focus and the
original closing guard intact. A separate real long-filename batch deletion
produces a result larger than the event budget; a temporary detail-read failure
must offer same-task retry and reveal the retained result without another delete
submission.

Map reload observes real stage payloads through the owned proxy and verifies one
shared connection, no discovery polling, at most one initial detail read and a
settled inline result. The final palette status and task result independently
verify actual prerequisite generation. Prune expiry remains a real backend
deadline; streamed availability disables subsequent application without polling.

`navigation.spec.ts` verifies native middle/ControlOrMeta navigation from sidebar,
styled fixed destinations and advanced-search links. Real new pages retain session
access and reach encoded directory/filter URLs; the source keeps its route,
sidebar expansion, search draft and checked paths. Explicit new-tab links isolate
their opener. Ordinary result navigation still closes the dialog and creates one
history entry. Search-file bytes and owned popup/file cleanup are independently
checked. Breadcrumb, parent-directory and directory-name links also retain source
selections during new-tab navigation and clear them during ordinary navigation.
File-tree geometry and Monaco journeys retain their existing action
assertions while querying navigation entries as links.

Browser journeys cover file read/save failure with exact-byte retry and deliberately empty saves; real Compose version conflicts and background completion after navigation; session retry/logout and actual console commands after reconnection; disconnected world-task observation with retained blocking, successful backend completion and a later edit that rollback must overwrite from the safety snapshot; and server-enforced prune expiry with unchanged region hashes. Transport faults occur in Playwright routing or an owned HTTP proxy. Version changes, task states, restore history and expiry remain real backend decisions. Each case sets its required lifecycle state and restores it in fixture teardown; file/configuration edits have explicit cleanup. Failure does not skip later cases. `BROWSER_REVERSE_ORDER=1` reverses journey registration to verify independence in a second fresh deployment; local runs retain their explicit related-case selection.

### Editor behavior

The Monaco journey uses the built server Compose and new-template editors without replacing Monaco, workers or schema responses. Real clipboard pastes retain multiline YAML indentation; visible target text must appear before keyboard navigation changes the selection and can cancel asynchronous paste. Invalid YAML produces error decorations, keyboard navigation opens diagnostic hover, valid Compose restores clean diagnostics, and schema hover and `MEMORY` completion exercise the loaded Minecraft schema. Navigating between editors and reopening both verifies worker availability after disposal and remount; worker-related console errors and uncaught exceptions fail the case. Drafts are never submitted, and API reads verify that server configuration and the template list remain unchanged.

### Directory upload

The directory upload journey selects an owned directory through a native browser `webkitdirectory` input, retaining its real `File` objects, relative paths and bytes. The test driver delivers those files through the document drop handler's files fallback because synthetic drops cannot supply operating-system directory entries. No upload hook, dialog, policy request or multipart request is replaced. Unchecking a directory must submit false decisions for both its immediate and nested descendants while the outside directory stays selected; three files with the same basename retain distinct paths. The final API reads and owned host files prove that unchecked content remains intact and the selected file receives its original upload bytes.

### Recovery and cleanup

The restore journey holds the real map-status request until the completed history row is visible, then releases it and verifies that the same open drawer still offers rollback after the map tabs appear. No map or history response is fabricated. A Query/MSW integration test also drives this transition through the real selection panel, history dialog and rollback task.

The restore journey and lifecycle fixture use `browser/cleanup.ts` to attempt every declared cleanup without replacing the original assertion failure. If both the journey and cleanup fail, the report includes their original stacks, with the journey failure first; a cleanup-only failure still fails the case. The wrapper separately reclaims the owned deployment and records that outcome in its manifest.

### File selection and rule feedback

The file-layout cases retain the actual server-rule GET response behind a transport gate. Batch toolbars sit below file-list and advanced-search results and take no space for empty selections. Selecting, clearing selections and checking/allowed/ignored transitions preserve result row geometry; while files are selected, rule transitions also preserve batch-toolbar geometry. All file controls share one rule read and submit no per-path check POST; navigating away and back refreshes a changed configuration while retaining the client cache. Disabled snapshot controls expose their reason only through tooltips; download and packing remain available. Each case owns its source files and ignore configuration and restores both during cleanup.

### Task acceptance and file recovery

Lifecycle acceptance has a dedicated journey: actual Docker startup returns 202; delaying delivery of real task-detail responses keeps the original controls blocked, exposes the reason/task-center link, and releases controls only after confirmed completion. The transport gate never fabricates task or server state.

The journey opens the task center from the pending operation's status region;
an observation-failure notification may independently offer the same action.
Cleanup restores observation and waits for the accepted task's real terminal
state before restoring the server, while preserving the original assertion
failure alongside any cleanup errors.

The file recovery journey creates a mixed-selection snapshot from the actual UI, checks source-specific skips and preview bytes, restores after a reload, and rolls back through filtered history after removing the current ignore rule. Individually ignored directories remain disabled; mixed selections skip them and rollback retains their recorded protection. File and map reload cases temporarily stop the next Restic backup worker only inside their owned application container, using a verified PID handle; they release it after checking resumed progress and close guards. The helper resumes automatically on input closure or its bounded timeout, and declared cleanup awaits its exit. These cases retain real task and filesystem results rather than synthesizing a running response.

The batch journey checks one multi-path snapshot with notes, restores only selected files, packs the same scope and deletes it while preserving unselected bytes. Directory-export cases replace only the directory picker with an owned native Chrome OPFS directory handle; native writable streams and real manifest/file APIs produce outputs inspected for exact bytes, empty directories and safe flat-name collisions. Advanced-search grouping checkboxes aggregate matching descendant paths while preserving selections outside the group; manifests contain those exact paths without treating a synthetic parent directory as the operation scope, so unmatched sibling files remain intact. They also check navigation while downloading and unsupported-browser tooltips with packing still available. The overview player case uses owned log/usercache inputs and public player APIs to verify keyboard opening and keeping the detail dialog after logout.

## Timed CI shards

The browser workflow collects every current Playwright case before planning, without launching Chromium or creating a world. `browser/shardReporter.ts` records project, file relative to Playwright's `rootDir`, and the full title path. The loop-declared journeys share a source line, so line numbers cannot select them independently. Frozen `--test-list` entries use these complete identities. The separate Node reporter tests are excluded from Playwright collection.

The workflow restores costs through the shared timing-history transport; `scripts/ci/browser_shards.py` chooses up to 16 shards, with at most 16 jobs concurrent. Each job uses its own Go wrapper, run ID, world and cleanup journal; Playwright keeps one worker, no retries and serial execution. Unmarked cases in the same file form an atomic group. Explicit `shard_group` annotations join shared fixture or serial cases; only cases declaring `shard_isolation=independent` may split from their file. The current journeys and observations make that declaration and retain their own cleanup.

The 300-second soft target covers wrapper world setup, the child Playwright command and owned cleanup. It excludes checkout, dependency installation, candidate OCI loading and Chromium installation. `fixture-result.json` contains separate `setup_seconds`, `command_seconds` and `cleanup_seconds`; Playwright case durations include their test fixtures, and the command residual accounts for runner and shared hook overhead. History repeats setup, cleanup and command overhead in each proposed shard. Missing history or new cases use positive fallback costs. Oversized atomic groups, fixed overhead that already exceeds the target, and the shard limit are reported without shortening test deadlines. When fixed overhead alone prevents the target, the planner uses one world rather than multiplying that overhead.

`browser-test-plan` freezes the complete inventory, historical source and plan. `browser-results-N` retains case results and redacted wrapper/candidate evidence for seven days. The aggregate audit accepts a single artifact extracted at the download root and multiple artifacts extracted into named subdirectories. It requires every current case exactly once, matching plan/history/candidate identities, passed outcomes without retries, distinct owned runs and complete cleanup. Only a successful audit and successful shard jobs publish `timing-history-browser/history.json` for 90 days. The next compatible run restores that evidence once; timing history changes placement and estimates, never the current inventory. Compatibility includes the dependency lockfile, Dockerfile, world recipe, measurement version and worker policy. `browser-coverage` retains the aggregate audit for 14 days.

## Comparable observations

When request/cache observations are directly related to the change, use the owned wrapper with `pnpm exec playwright test browser/00-observations.spec.ts --grep @observations`. It records identical overview/detail/map windows on both the original source build and current candidate. In a complete CI browser run, `00-observations.spec.ts` runs before modifying workflows, so its first map view starts with the fresh owned environment's cache. It observes overview polling for 15 seconds, server detail for 5 seconds after navigation, first map display, reload of the same view, and a further 15-second idle window. Attachments contain endpoint counts, statuses, failures, durations and response-body byte counts, without headers, bodies or query strings. Actual region coordinates/hashes, viewport, browser, client provenance and image IDs accompany the observations.

Run the original source image and candidate in separate owned deployments using the same Chromium, world recipe, visible dimension/view and client cache. Worlds do not have a fixed seed, so geometry and bytes can differ; this is an observed request comparison, not a controlled rendering benchmark. Preserve each run, including failures, rather than retrying business operations inside a case. Compare only successful observation results:

```bash
node scripts/compare-browser-observations.mjs \
  /tmp/baseline-browser/results.json \
  /tmp/candidate-browser/results.json \
  /tmp/browser-comparison.json
```

The comparison requires a matching browser, viewport and ordered measurement windows. It includes before/after context and raw endpoint summaries, then computes deltas; it does not manufacture a baseline or enforce an arbitrary performance threshold. Map windows include navigation, readiness checks and a fixed three-second settling period, so their total durations are not rendering-only timings. Navigation cancellations and incomplete requests remain visible, and stable idle windows should be assessed separately from page transitions.
