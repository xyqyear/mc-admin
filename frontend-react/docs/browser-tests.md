# Owned browser verification

`browser/` drives the built application in Chromium through real routes, Monaco, dialogs, HTTP, WebSockets and Leaflet. No business hook or QueryClient is replaced. `playwright.config.ts` uses one worker, no retries, and retains screenshots/traces for failed tests. The Go runner owns deployment, credentials, resource leases and cleanup; tests cannot attach to an arbitrary application.

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

The wrapper writes a private `MC_ADMIN_BROWSER_FIXTURE` JSON containing the owned URL, credentials, server path and image/environment/manifest identities. Tests validate its local URL, directory ownership and private permissions. Never publish the runtime directory or private fixture. Publish the runner's redacted report/cleanup evidence and the Playwright results/report/artifacts; traces belong to short-lived test credentials and should still have restricted retention.

Browser journeys cover file read/save failure with exact-byte retry and deliberately empty saves; real Compose version conflicts and background completion after navigation; session retry/logout and actual console commands after reconnection; disconnected world-task observation with retained blocking, successful backend completion and a later edit that rollback must overwrite from the safety snapshot; and server-enforced prune expiry with unchanged region hashes. Transport faults occur in Playwright routing or an owned HTTP proxy. Version changes, task states, restore history and expiry remain real backend decisions. Each case sets its required lifecycle state and restores it in fixture teardown; file/configuration edits have explicit cleanup. Failure does not skip later cases. `BROWSER_REVERSE_ORDER=1` reverses journey registration to verify independence in a second fresh deployment; local runs retain their explicit related-case selection.

The directory upload journey selects an owned directory through a native browser `webkitdirectory` input, retaining its real `File` objects, relative paths and bytes. The test driver delivers those files through the document drop handler's files fallback because synthetic drops cannot supply operating-system directory entries. No upload hook, dialog, policy request or multipart request is replaced. Unchecking a directory must submit false decisions for both its immediate and nested descendants while the outside directory stays selected; three files with the same basename retain distinct paths. The final API reads and owned host files prove that unchecked content remains intact and the selected file receives its original upload bytes.

The restore journey holds the real map-status request until the completed history row is visible, then releases it and verifies that the same open drawer still offers rollback after the map tabs appear. No map or history response is fabricated. A Query/MSW integration test also drives this transition through the real selection panel, history dialog and rollback task.

The restore journey and lifecycle fixture use `browser/cleanup.ts` to attempt every declared cleanup without replacing the original assertion failure. If both the journey and cleanup fail, the report includes their original stacks, with the journey failure first; a cleanup-only failure still fails the case. The wrapper separately reclaims the owned deployment and records that outcome in its manifest.

`MC_ADMIN_BROWSER_CLIENT_METADATA` optionally names a JSON file with `{path,url,version,sha1,size}` for an official Minecraft client. Tests verify the official download host, SHA1 and byte count before copying it into the owned server's map cache. Production palette generation and rendering still run normally. This fixture avoids repeated external downloads; it never supplies fabricated JARs, palettes or PNGs. Without it, the application downloads its normal dependency.

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

Lifecycle acceptance has a dedicated journey: actual Docker startup returns 202; delaying delivery of real task-detail responses keeps the original controls blocked, exposes the reason/task-center link, and releases controls only after confirmed completion. The transport gate never fabricates task or server state.

The file recovery journey creates a snapshot from the actual UI, checks preview bytes, restores after a reload, and rolls back through filtered history. Ignored directories remain disabled and protected. File and map reload cases temporarily stop the next Restic backup worker only inside their owned application container, using a verified PID handle; they release it after checking resumed progress and close guards. The helper resumes automatically on input closure or its bounded timeout, and declared cleanup awaits its exit. These cases retain real task and filesystem results rather than synthesizing a running response.

The batch journey checks one multi-path snapshot with notes, restores only selected files, packs the same scope and deletes it while preserving unselected bytes. Directory-export cases replace only the directory picker with an owned native Chrome OPFS directory handle; native writable streams and real manifest/file APIs produce outputs inspected for exact bytes, empty directories and safe flat-name collisions. They also check navigation while downloading and unsupported-browser tooltips with packing still available. The overview player case uses owned log/usercache inputs and public player APIs to verify keyboard opening and keeping the detail dialog after logout.
