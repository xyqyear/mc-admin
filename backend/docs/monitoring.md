# Shared runtime monitoring

`GET /api/monitoring` is an authenticated read model for host resources and
registered servers. It returns recent observations without starting Docker
commands, a CPU measurement window or a directory traversal. The current ACTIVE
registry filters server generations on every request; maintenance is projected
from the existing admission, active task and lock owners.

## Ownership and scheduling

`Runtime.monitor` owns three concrete workers: host samples, server/container
samples and directory sizes. `Runtime.docker_reader` owns the serialized Docker
SDK client and its single worker thread. Startup begins observation after
operation recovery without waiting for the first sample. Shutdown stops sampling
and drains actual work before closing Docker and database dependencies. Sampling
does not inherit an initiating operation context. Cleanup errors are reported,
not converted into successful shutdown.

Host and container workers target a two-second period. Each worker completes its
current round before another starts; missed rounds do not accumulate. Directory
statistics run one at a time and wait at least 60 seconds after completion before
repeating for a server. A slow source does not block HTTP or the independent host
worker. Sampling continues without browser clients and has a fixed idle cost.

The Docker reader lists Compose containers once per server round and inspects
each selected container once. Project labels, working directory, service and
configured container identity determine ownership. Explicit Compose names and
additional services retain their status semantics. Direct command guards use
fresh Engine observations; cached monitoring never grants permission to mutate
worlds, files or container state. Compose continues to execute lifecycle commands. Query/RCON use the independent
[command executor](minecraft.md#container-commands), so slow commands do not occupy
the monitoring reader.

The UI submits `start` as startup intent. Under the operation lease, the command
checks live container existence and creates missing containers with Compose up,
or starts existing containers without reconciling changed Compose configuration.
The UI never chooses between these operations from a cached status. Explicit
`up` remains a Compose reconciliation operation.

## Samples and identity

Each sample contains `value`, `sampled_at`, `quality` and `error`. Quality is
`pending` before an effective sample, `ready` after success, `stale` when a prior
sample is retained after failure or expiry, and `unavailable` when no usable value
exists. Fast values expire after six seconds and directory statistics after 120
seconds. Reading an expired sample does not change its timestamp. Stopped
containers have unavailable runtime metrics rather than synthetic zero values.

Server entries carry the persisted `generation` and an opaque `incarnation`
derived from container ID and start time. CPU baselines additionally bind the
Java PID and its process start identity. Recreating a server, restarting a
container or replacing its process resets the applicable baseline. Slow results
revalidate their captured `ServerRef` before publication. Samples are held only
in memory; no database migration, history table or backfill is required.

| Metric | Meaning |
| --- | --- |
| Server `cpu_percent` | Delta of Java user + system CPU seconds divided by actual monotonic elapsed time; one core is 100%, multiple cores can exceed 100% |
| Host `cpu_percent` | Busy/total CPU counter delta, excluding duplicate guest time and idle/iowait from busy time; 0–100% |
| Server `memory_bytes` | Existing cgroup `anon + file`, not JVM heap or Docker CLI cache-adjusted memory |
| `disk_io` / `network_io` | Cumulative read/write or receive/send bytes for the observed running instance |
| Server `disk` | `du -sb` apparent directory bytes plus filesystem capacity and available bytes |
| Host `memory`, `load`, `disk` | Host memory bytes, three load averages and filesystem byte counts |

The first CPU counter establishes a baseline and remains pending. An invalid
interval or a changed process resets that baseline. Java discovery uses the
Engine process list, not the container init PID. Subsequent counter reads verify
the process identity, Java name and container membership.

Maintenance precedence is recovery block, active lifecycle task, deletion
freeze, then maintenance holder. The projection scans active tasks once for the
server batch. It is current at the HTTP read and does not wait for a terminal
operation notification. Task acceptance and observation are still distinct from
settlement; [operation recovery](operation-recovery.md) owns writer guarantees.

## Verification

Targeted coverage lives in `test_docker_reader.py`, `test_runtime_monitoring.py`,
`test_process_resources.py`, the owned Docker `test_monitoring.py`, and affected
Runtime/lifecycle tests. Public API scenarios include
`system.metrics-static-validation` and `minecraft.shared-monitoring`; the
[coverage inventory](../../e2e/docs/coverage.md) records their assertions.
