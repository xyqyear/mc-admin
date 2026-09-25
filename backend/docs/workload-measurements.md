# Workload measurements

Performance observations use the same synthetic inputs and fixed external binaries
on both sides of the application-boundaries refactor. They record behavior and
latency separately; sample counts, route coverage and file sizes are not release
thresholds. Measurements on a shared development host describe these fixtures,
not production capacity.

## Native comparison

`tests.support.workload_baseline` runs the public archive protocol through an
in-process ASGI transport and invokes real fd, Restic and mcmap adapters. The
baseline application comes from the actual Git source at
`9cf6f77b258a7ccf4507c51cb686a45f8f74d823`, imported in a disposable subprocess;
the candidate uses its own explicit runtime. Neither run starts background
producers. Both use Python 3.13.7 and the Dockerfile versions: fd 10.4.2,
Restic 0.18.1 and mcmap 0.8.4. Explicit binary paths avoid accidentally comparing
the host's fd 10.3.0 and Restic 0.18.0 with the container versions.

From `backend/`, with the three binary path environment variables pointing to
these versions:

```bash
uv run python -m tests.support.workload_baseline --samples 3 \
  --app-ref 9cf6f77b258a7ccf4507c51cb686a45f8f74d823 --output /tmp/workload-before.json
uv run python -m tests.support.workload_baseline --samples 3 \
  --label candidate-source-fingerprint --output /tmp/workload-after.json
```

The recorded three-sample medians are:

| Workload | Before | After | Behavioral result |
| --- | ---: | ---: | --- |
| 4 MiB resumable upload, hash and publication | 21.018 ms | 22.448 ms | Same 10 requests, stale offset 409, completed retry 200, hash and published bytes |
| Search 256 files containing 1 MiB in total | 54.824 ms | 71.748 ms | Same 256 paths and total size |
| 4 MiB Restic backup and restore | 5.061423 s | 5.095129 s | Same restored hash and two restore events |
| Remove an empty chunk from an 8 KiB region | 1.861 ms | 11.686 ms | Same `chunk_removed`/`result` protocol and retained region bytes |

Full samples, binary versions and behavioral fingerprints are in
[`evidence/phase7-native-workloads.json`](evidence/phase7-native-workloads.json).
Peak RSS is process-wide and includes imports and all workloads; it is not a
per-request memory measurement. The empty-region operation checks a real mcmap
protocol, not map rendering speed.

The largest relative change occurs in a command that originally took under
2 ms. An additional 12 alternating pairs compared the same pinned `mcmap
--version` invocation through direct subprocess startup and the owned executor:
their medians were 0.672 ms and 9.569 ms. The owned executor starts a gated
process, records its identity before admitting execution, and confirms exit
before releasing ownership. This measured startup/finalization cost explains
most of the empty-chunk difference; it also contributes to file search latency.
The search samples overlap (42–77 ms before, 71–84 ms after), so the remaining
variation cannot be attributed precisely on this shared host. These observations
do not justify removing process ownership or claiming that world-scale rendering
has the same overhead ratio.

## Deployed HTTP comparison

`tests.support.deployed_workload` uses only public HTTP endpoints against the
Go runner's owned Backup recipe. It requires the private
`MC_ADMIN_BROWSER_FIXTURE` document and refuses non-loopback targets. Reports
include image config ID, environment identity, request counts, body byte counts,
latency samples and content hashes, excluding credentials and response contents.

Run each image sequentially from the repository root:

```bash
e2e/bin/mc-admin-e2e browser --backend-image IMAGE_CONFIG_DIGEST \
  --recipe backup --output /tmp/workload-runs --run-id UNIQUE_RUN_ID -- \
  uv run --directory backend python -m tests.support.deployed_workload \
    --label SOURCE_IDENTITY --samples 3 --output /tmp/deployed-workload.json
```

The upload repeats the native protocol and adds one public archive download to
verify the final bytes, giving 11 requests. The ordinary-file restore creates
a 4 MiB ASCII file, takes a real Restic snapshot, changes the file, restores it
through the finite SSE endpoint and downloads the result. It verifies the
terminal event and retained safety snapshot. Its seven requests include fixture
preparation; per-request timings distinguish backup and restore from setup and
verification. These are ordinary-file operations, independent of a live world's
rendering and write load. The wrapper owns the application, mounts, network and
port leases and cleans them after success, child failure or timeout.

The initial deployed comparison measured 148.477 ms versus 175.961 ms for the
upload and 5.136702 s versus 6.245191 s for the complete backup/restore workload.
All content hashes, request counts and SSE event types matched. The restore
request itself rose from 3.558534 s to 4.468257 s. Full per-request observations
and candidate identity are retained in
[`evidence/phase7-deployed-workloads.json`](evidence/phase7-deployed-workloads.json).

A separate real restore traced only its owned backend process tree. Its Restic
sequence was backup, two snapshot reads, a parent listing, a target-directory
listing and restore. The target listing is required to distinguish a recorded
empty directory: restoring an empty subtree with Restic alone does not remove
live content, so the planner must select the explicit empty-content operation.
The extra listing took approximately 0.788 s in the trace. Three alternating
read-only probes in the same container/repository measured a 0.687 s median for
that listing, excluding Docker command startup and the application's process
gate. This accounts for most of the 0.910 s restore difference. The remaining
0.12–0.22 s cannot be assigned precisely between ownership/journal work and host
variation from these samples. The extra metadata read preserves the empty-world
and ignored-file guarantees; it is an explicit correctness cost, not a reason to
silently accept arbitrary latency growth. Trace/probe evidence is in
[`evidence/phase7-restic-attribution.json`](evidence/phase7-restic-attribution.json).

After the console/editor, pristine configuration refresh and offline SQLite
lifetime fixes, the final candidate was measured again through the same public
workloads: upload 185.732 ms and the complete backup/restore workflow 6.301501 s.
The restore request itself took 4.455696 s, consistent with the investigated
initial difference. All three samples again preserved
the baseline request counts, final byte hashes, safety references and terminal
events. The final image/source identity and all request timings are in
[`evidence/phase7-final-deployed-workloads.json`](evidence/phase7-final-deployed-workloads.json).
The initial comparison, [superseded candidate 3 measurements](evidence/phase7-candidate3-deployed-workloads.json)
and process trace remain separate diagnostic observations;
they are not silently relabeled as measurements of the final image.

Real browser observations cover navigation, map requests and rendering through
the Playwright suite in `frontend-react/browser/`. Browser and HTTP measurements
must identify the tested image and actual baseline rather than compare a current
run with an invented expected count.
