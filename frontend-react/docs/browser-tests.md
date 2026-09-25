# Owned browser verification

`browser/` drives the built application in Chromium through real routes, Monaco, dialogs, HTTP, WebSockets and Leaflet. No business hook or QueryClient is replaced. `playwright.config.ts` uses one worker, no retries, and retains screenshots/traces for failed tests. The Go runner owns deployment, credentials, resource leases and cleanup; tests cannot attach to an arbitrary application.

Install Node 24 dependencies with `pnpm install --frozen-lockfile`, then `pnpm exec playwright install --with-deps chromium`. Run from this directory against the Docker config ID loaded from the release candidate OCI artifact:

```bash
BROWSER_OUTPUT_DIR=/tmp/browser-report \
  /path/to/mc-admin-e2e browser \
  --backend-image sha256:CANDIDATE_CONFIG_ID \
  --minecraft-image itzg/minecraft-server:java25-e2e-local-vanilla-1.21.11-64bb6d763bed \
  --output /tmp/browser-runs --run-id e2e-browser-unique \
  -- pnpm test:browser
```

The wrapper writes a private `MC_ADMIN_BROWSER_FIXTURE` JSON containing the owned URL, credentials, server path and image/environment/manifest identities. Tests validate its local URL, directory ownership and private permissions. Never publish the runtime directory or private fixture. Publish the runner's redacted report/cleanup evidence and the Playwright results/report/artifacts; traces belong to short-lived test credentials and should still have restricted retention.

Five workflows cover file read/save failure with exact-byte retry and deliberately empty saves; real Compose version conflicts and background completion after navigation; session retry/logout and actual console commands after reconnection; interrupted world restore with a distinct post-interruption edit that rollback must overwrite from the safety snapshot; and server-enforced prune expiry with unchanged region hashes. Transport faults occur in Playwright routing or an owned streaming proxy. Version changes, task states, restore history and expiry remain real backend decisions. Each case sets its required lifecycle state and restores it in fixture teardown; file/configuration edits have explicit cleanup. Failure does not skip later cases. `BROWSER_REVERSE_ORDER=1` reverses the five workflows to verify their independence in a second fresh deployment.

The restore journey and lifecycle fixture use `browser/cleanup.ts` to attempt every declared cleanup without replacing the original assertion failure. If both the journey and cleanup fail, the report includes their original stacks, with the journey failure first; a cleanup-only failure still fails the case. The wrapper separately reclaims the owned deployment and records that outcome in its manifest.

`MC_ADMIN_BROWSER_CLIENT_METADATA` optionally names a JSON file with `{path,url,version,sha1,size}` for an official Minecraft client. Tests verify the official download host, SHA1 and byte count before copying it into the owned server's map cache. Production palette generation and rendering still run normally. This fixture avoids repeated external downloads; it never supplies fabricated JARs, palettes or PNGs. Without it, the application downloads its normal dependency.

## Comparable observations

`pnpm test:browser --grep @observations` records identical overview/detail/map windows on both the original source build and current candidate. The `00-observations.spec.ts` file runs before modifying workflows, so its first map view starts with the fresh owned environment's cache. It observes overview polling for 15 seconds, server detail for 5 seconds after navigation, first map display, reload of the same view, and a further 15-second idle window. Attachments contain endpoint counts, statuses, failures, durations and response-body byte counts, without headers, bodies or query strings. Actual region coordinates/hashes, viewport, browser, client provenance and image IDs accompany the observations.

Run the original source image and candidate in separate owned deployments using the same Chromium, world recipe, visible dimension/view and client cache. Worlds do not have a fixed seed, so geometry and bytes can differ; this is an observed request comparison, not a controlled rendering benchmark. Preserve each run, including failures, rather than retrying business operations inside a case. Compare only successful observation results:

```bash
node scripts/compare-browser-observations.mjs \
  /tmp/baseline-browser/results.json \
  /tmp/candidate-browser/results.json \
  /tmp/browser-comparison.json
```

The comparison requires a matching browser, viewport and ordered measurement windows. It includes before/after context and raw endpoint summaries, then computes deltas; it does not manufacture a baseline or enforce an arbitrary performance threshold. Map windows include navigation, readiness checks and a fixed three-second settling period, so their total durations are not rendering-only timings. Navigation cancellations and incomplete requests remain visible, and stable idle windows should be assessed separately from page transitions.

## Recorded source-to-candidate observation

[Sanitized observation evidence](evidence/phase7-browser-comparison.json) compares the actual `9cf6f77` source image (`df8b8bdc…42dc`) with candidate 4 (`479e7c02…4d8d`). Both ran Chromium 153.0.8010.12 at 1440×1000 with four visible world regions and the verified official 1.21.11 client. The evidence contains complete image IDs, region hashes, endpoint/status/byte summaries and source report locations; it excludes request bodies, cookies, credentials and query strings.

| Window | Original requests | Candidate requests | Original / candidate failed requests |
| --- | ---: | ---: | ---: |
| Overview, 15 seconds | 17 | 20 | 0 / 0 |
| Server detail after overview, 5 seconds | 22 | 13 | 0 / 0 |
| First map view | 21 | 24 | 0 / 1 |
| Same map view after reload | 21 | 24 | 0 / 1 |
| Map idle, 15 seconds | 20 | 21 | 0 / 0 |

The application-wide operation observer adds journal polling; the two candidate map navigation windows each contain one `/api/operations` request that ended without a response during navigation. These cancellations remain counted as failures, rather than being removed from the comparison. Both stable 15-second windows have zero failed requests. The detail window observes fewer requests with shared query caching, but this single sample is not a statistical estimate. World seeds and region hashes differ between deployments, so neither PNG byte changes nor rendering durations are attributed solely to application code.
