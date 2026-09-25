# Server configuration (`app.configuration`)

The configuration feature owns preparation, versioned reads, Compose replacement
and matching template metadata. HTTP routes authenticate and validate requests;
the application service owns resource leases, durable phases and necessary
cleanup. Callers import the feature’s preparation and application boundaries
directly. Server creation uses the same preparation functions within its bundled
lifecycle; reusable template management remains in `app.templates`.

## Prepared configuration and legacy input

`ServerConfiguration` is immutable. It holds rendered YAML, serialized snapshot
and variable values, and an optional expected version. Accessors deserialize
fresh objects so later mutation of a form dictionary or snapshot cannot change
an accepted plan. Template preparation overlays authored values on snapshot
defaults, validates values and renders once. The YAML, snapshot and values are
then passed together through application and metadata persistence.

Existing template servers use their retained snapshot even if the source template
changes or is deleted. Explicit conversion to a chosen live template captures its
snapshot and source update time. Direct mode has no template association. Strict
game-port initialization rules belong to reusable template saves and new-server
creation; existing configuration reads and rebuilds retain the permissive Compose
parser. Preparation does not rewrite historical snapshots or add missing
initialization settings automatically.

## Versions and HTTP compatibility

`ConfigurationState` contains the current server generation, canonical Compose
target path, raw file bytes and retained template metadata. Its opaque `version`
hash includes all four. Formatting-only file changes, source metadata changes,
same-name server recreation and switching an internal Compose symlink to a
different target therefore change the version. Clients must treat it as an
opaque comparison value, not a content hash they can calculate themselves.

Compose and template-configuration reads return `version`; variable extraction
and conversion-check responses return the version of the Compose they examined.
Compose saves, template-variable saves and both mode conversions accept optional
`expected_version`. A stale preflight request returns HTTP 409 with:

```json
{
  "detail": {
    "code": "configuration_conflict",
    "message": "配置已被其他操作修改，请重新比较后提交",
    "current_version": "opaque-current-version"
  }
}
```

The worker checks the version again after acquiring its lease. A conflict found
after task acceptance keeps the existing `failed` task status and string error,
with optional `error_code="configuration_conflict"` in task detail and summary.
The journal retains that failure code across restart. The client can retain its
draft, fetch the current configuration, compare and submit against a fresh version.

Clients omitting `expected_version` retain last-write-wins behavior for serialized
application requests. Every operation still rechecks its captured state before
replacement and refuses an intervening change. Existing task IDs, status enums,
server URLs and authentication/CSRF rules remain in use.

## Application sequence

`rebuild_server_task` acquires the server maintenance lease and the shared port
allocation lease. It revalidates the accepted `ServerRef` before mutation, reads
the baseline, checks the requested version, validates the rendered configuration
and checks ports. It then captures the original running intent and hash evidence.

The consequential phases proceed in this order:

1. Register and write the owned staging file, then recheck the baseline.
2. Bring down a running or stopped-but-created container. A server without a
   container skips this step.
3. Revalidate the generation and baseline, and confirm that no container remains.
4. Atomically replace Compose and record `configuration_written`.
5. Verify the written bytes and unchanged previous source, then commit the
   matching template ID, snapshot and values in a short database transaction.
6. Start the server only when its captured intent was running, and finish cleanup.

No SQLite write transaction remains open across Docker commands or filesystem work.
An initially stopped server remains stopped, including when its old stopped
container needed removal. Metadata must commit before startup. A later failure
does not undo a completed file replacement or metadata commit automatically.
The terminal result reports ports, the captured running intent and the resulting
configuration version.

Template-to-direct conversion preserves Compose and clears source metadata.
Direct-to-template conversion can skip rebuilding when the prepared YAML is
semantically equal to the current file. These metadata-only changes still acquire
maintenance ownership, reread the baseline, check the version and write a durable
`configuration_apply` operation before committing metadata. A conversion requiring
different YAML submits the normal `server_rebuild` task.

## Staging and interruption

The staging file is created with exclusive creation and mode `0600` beside the
canonical Compose target. An internal symlink pointing into a subdirectory or
another mounted directory still stages on that target's filesystem. The writer
preserves the original file's owner and mode, flushes and fsyncs its bytes, then
uses `os.replace` and fsyncs the containing directory.

Before file creation, the journal retains a `configuration_stage` resource with
the existing server generation and exact project-relative path, plus a token
recovery reference. Artifact registration cannot introduce another server or
generation. The journal stores paths and hashes, never YAML, variables or secrets.
Finalization waits for started filesystem threads and metadata commits despite
cancellation; the maintenance lease remains held through necessary cleanup and
failure reconciliation.

Normal `finally` cleanup unlinks the exact stage and resolves its reference.
Startup retries unresolved stage cleanup, including records already terminal.
It first confirms writers stopped and checks generation and path confinement;
redirected parent symlinks are refused. It does not search directories by prefix
or use the current Compose symlink to guess the original stage location. Records
without an artifact path retain the project-root-plus-token compatibility lookup.
Failed cleanup keeps its evidence for later reconciliation and retention.

## Recovery and operating limits

The journal records the baseline configuration version, the intended YAML hash
and the intended source-metadata hash. Configuration consistency is checked only
when `data_changed` is set; an interruption during validation or staging must not
require unapplied target YAML to replace an unchanged valid baseline.

After writers stop, recovery can verify either the complete original baseline or
the intended configuration with its matching source metadata. An inconsistent or
unverifiable file/source pair keeps a visible admission block. An OWNER can
explicitly resolve verified configuration work with `configuration_reconciled`;
the original failure or interruption remains in history. Recovery neither replays
the rebuild nor starts the server automatically. Restoring old bytes alone is
insufficient when source metadata no longer matches that baseline. See
[operation recovery](operations.md) for the resolution API.

The supported deployment has one backend writer per database and server root.
Application leases serialize managed writes; version checks also detect external
edits observed before replacement. An external tool can still change files after
the final check and before `os.replace`: the filesystem does not provide a shared
compare-and-swap transaction with those tools, SQLite or Docker. Coordinate direct
file edits with the application; this design does not promise cross-system atomic
rollback or protection against arbitrary concurrent external writes.

The application-level frontend operation observer refreshes registered
configuration, template-mode, task and server queries for terminal outcomes,
including failures with partial writes, independently of the initiating page.
Editor drafts are retained separately from that refreshed remote state.

## Files and verification

- `preparation.py` — immutable prepared values, defaults, rendering and validation.
- `state.py` — versioned reads, conflicts and source-metadata persistence.
- `files.py` — owned staging, file replacement and finite cleanup.
- `application.py` — rebuild and metadata-only conversion use cases.

`tests/configuration/` exercises preparation isolation, original running intent,
faults at durable phase boundaries, cancellation during real filesystem work,
source reconciliation and staging recovery. Server/template route tests cover
version-aware and legacy request shapes; migration and cron tests cover the
independent generation-bound restart plans described in [cron.md](cron.md).
