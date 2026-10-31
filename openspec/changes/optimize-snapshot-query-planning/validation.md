# Validation evidence

## Local verification, 2026-10-31

All execution used the local Windows checkout, Linux-owned backend dependencies
and owned Docker fixtures. Production and map compatibility were outside scope.

- Backend: 18 selected coverage/mixed-exclusion/safety-source cases passed;
  32 selected disconnect, logical protection, world command/absence/endpoint,
  import-boundary and API-contract cases passed; 20 source-index, candidate and
  historical coverage cases passed. Existing generic-file alias tests remain.
- Independent assertions and an exhaustive test-only reference agree on source
  order, notes, exclusions, missing coverage, negative-coordinate MCC evidence,
  skip truncation and full skip counts. Selecting an MCA as an ordinary file
  does not add unselected MCC siblings.
- Real Restic/mcmap regressions exercise world, dimension, region and chunk
  recovery, safety snapshots and rollback, including external MCC bytes and
  missing entity/POI directories. Disconnect testing confirms the owned read
  process exits, an independent SQLite write succeeds and a fresh query works.
- Frontend: 12 targeted candidate, recovery observation and preview tests passed.
  Native XHR abort is observed on selection change/last-observer close; shared
  observation and reopen behavior remain covered.
- Ruff, Pyright, frontend lint/types/boundaries/contract freshness/bundle,
  affected Go vet/format and strict OpenSpec validation passed. Existing bundle
  size warnings remain. Local coverage is not a whole-suite coverage claim;
  complete coverage auditing belongs to qualification.

## Performance and deployed API

The pure matching benchmark uses 385 sources and six regions. Ordinary selection
contains 18 MCA mappings instead of 18,450 MCA/speculative-MCC mappings. Broad
recorded exclusions still expand the necessary evidence to retain exact counts.

| Source policies | Matching time, no coverage | Matching time, coverage enabled | Maximum scheduler gap, coverage enabled |
| --- | ---: | ---: | ---: |
| Identical metadata | 0.0027 s | 0.0062 s | 0.0110 s |
| Distinct exclusions | 0.1300 s | 0.4770 s | 0.0119 s |
| Broad protected directory | 0.1694 s | 0.3154 s | 0.0976 s |

These timings exclude repository listing and are not end-to-end production
speedup ratios. Tests require completion within five seconds and scheduler gaps
below 0.5 seconds, with separate outcome and cancellation assertions.

The deployed `world.snapshot-query-responsiveness` case passed both normal and
`--no-reuse` runs on image
`sha256:a124693d12dd3c0eaee7073eb9a3637c046722415757cca01b8e007165d3c4b7`.
Both used fresh owned environments. The 64-region query plus concurrent health
reads took 1475 ms and 1481 ms. Each case verified authentication, exact historical
MCC skips, unchanged query input bytes, real recovery and safety rollback.

Owned run IDs: `e2e-9d1f1c0f6d8d` and `e2e-ae9c6bd1745d`.

## Complete qualification

Required after committing and pushing: `Qualify and Publish Application` on the
implementation branch with `publish=false`, bound to the pushed SHA. Local
success does not satisfy this gate; the run and final audited outcome must be
recorded after completion.

First run: [41176222208](https://github.com/xyqyear/mc-admin/actions/runs/41176222208),
source `367120c9495fe482875619beaecce23a71223988`. Candidate/Go, all static and
frontend gates, all 14 backend shards and the backend coverage audit passed.
API/browser shards failed before test execution at candidate loading: the
containerd image store's local image ID differed from the OCI config digest.
Their audits and final qualification correctly failed. The CI setup now
explicitly selects classic `overlay2` for these disposable runtime runners,
preserving every candidate digest, outcome and cleanup assertion. Complete
qualification must be rerun for the resulting commit.
