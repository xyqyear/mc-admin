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
| Server `disk` | `du -sb` apparent directory bytes plus effective storage capacity and available bytes |
| Host `memory`, `load`, `disk` | Host memory bytes, three load averages and effective storage byte counts |

The first CPU counter establishes a baseline and remains pending. An invalid
interval or a changed process resets that baseline. Java discovery uses the
Engine process list, not the container init PID. Subsequent counter reads verify
the process identity, Java name and container membership.

Maintenance precedence is recovery block, active lifecycle task, deletion
freeze, then maintenance holder. The projection scans active tasks once for the
server batch. It is current at the HTTP read and does not wait for a terminal
operation notification. Task acceptance and observation are still distinct from
settlement; [operation recovery](operation-recovery.md) owns writer guarantees.

## Storage capacity and Btrfs quotas

`app.system.resources.get_disk_info` reads filesystem capacity with
`shutil.disk_usage`. Available space uses the operating system's available-byte
count, not total minus used. Backup repository usage and storage self-checks use
this same reader; server directory size remains a separate apparent-size metric.

On Linux Btrfs mounts, the reader identifies the containing mount and subvolume
from the mount table, then matches the mounted device to its filesystem under
`/sys/fs/btrfs`. It reads the kernel's qgroup counters without administrative
ioctls or additional container capabilities. With a referenced or exclusive
limit, total and used describe the limiting quota; available is the smaller of
filesystem availability and quota headroom after data and metadata reservations.
An exhausted or lowered quota has zero available bytes. Unrestricted filesystems
retain their filesystem statistics. API field names and units remain unchanged.
Storage self-checks use the greater of actual usage and unavailable capacity,
so low filesystem headroom or reservations can warn before the quota fills.

The reader rejects ambiguous filesystem identity, unmounted nested subvolumes,
unreadable counters and inconsistent accounting. Sysfs does not expose qgroup
parent relationships, so the reader also rejects filesystems with limited
higher-level groups instead of guessing their applicability. These failures
follow existing HTTP errors, monitoring sample quality and self-check warnings;
they never silently report the whole disk as available quota. Reported headroom
is an observation, not a reservation or a guarantee about future logical file
sizes after compression and concurrent writes.

## Verification

Targeted coverage lives in `test_storage_resources.py`, `test_docker_reader.py`,
`test_runtime_monitoring.py`, `test_process_resources.py`, the owned Docker
`test_monitoring.py`, and affected Runtime/lifecycle tests. Public API scenarios
include `snapshots.repository-and-selection`, `system.metrics-static-validation`
and `minecraft.shared-monitoring`; the
[coverage inventory](../../e2e/docs/coverage.md) records their assertions.
