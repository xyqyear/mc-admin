# Disposable deployment and rollback

`scripts/deployment_rehearsal.py` operates only inside a fixture created by the Go runner. It validates Docker run/environment labels before stopping or replacing a container, uses immutable local image IDs, and retains the original private credentials and persistent mounts. It does not connect to user deployments, construct a database schema, invoke a downgrade, or contact cloud DNS accounts.

Build the release image from the actual released source, including its frontend and migration files. A historical image is not the current application with its Alembic version changed. Prepare the candidate from the same OCI archive used by API and browser qualification; its loaded config digest identifies the Docker image to pass below.

```bash
mc-admin-e2e browser --backend-image <released-image-id> --recipe backup \
  --output /private/rehearsals --run-id release-upgrade-local -- \
  uv run --project backend python e2e/scripts/deployment_rehearsal.py \
  --candidate-image <qualified-candidate-config-digest> \
  --compatible-image <separately-retained-same-schema-image-id> \
  --output /private/rehearsal-result.json
```

The Backup recipe supplies the application, server configuration and real Restic repository. The script starts Minecraft using the shared operations API and verifies Docker health and the owned container's real RCON client. This avoids assuming that historical releases report the current health-status vocabulary. Log input and usercache identities produce real player sessions, messages and achievements; public APIs create users, a paused restart schedule, a template, ordinary files, an uploaded archive and world snapshots. User IDs, names and roles are checked individually. An equivalent noncapturing prefix in the dynamic chat-parser pattern provides a nondefault configuration value whose preservation is also checked.

All writers are stopped before copying the complete persistent directory. The checkpoint contains SQLite, dynamic configuration, server Compose and data, archives, and the Restic repository. Credentials remain private. The script upgrades the live directory and verifies historical IDs, contents and snapshots through APIs, then creates post-upgrade users, cron state, ordinary and world data, operation history and snapshots.

Rollback has three distinct boundaries:

1. **Old code on the upgraded schema.** A full upgraded copy is mounted into the released application. If the release does not know the new Alembic revision, startup must fail. The test compares every SQLite table's row digest and persistent-file digests before and after the attempt. It never silently restores an older database over new data.
2. **Complete checkpoint disaster recovery.** The released application starts with its matching complete pre-upgrade checkpoint. Released data must be available, while post-checkpoint data is correctly absent there. The complete upgraded copy remains separate during verification. This is a recovery to the checkpoint time and does not merge later changes. A successful same-schema historical-image replacement is recorded separately; it does not establish compatibility with arbitrary older code.
3. **World content recovery.** The candidate restores an explicit world snapshot, retaining a safety snapshot, then rolls that restoration back. World bytes change; unrelated files, users, cron definitions and player history remain present. Replacing application code alone does not restore world contents.

The current fixture uses v5.3.0, whose schema head is `2026060500`, and the candidate schema head `2026092503`. Direct v5.3.0 startup on the newer schema is outside the supported rollback range. The tested same-schema image is an explicitly recorded artifact; a matching Alembic head alone does not prove that every older application understands all stored semantics.

The public result contains image identities, actual application-source hashes, retained IDs, schema versions, hashed data evidence and the distinct outcomes. Checkpoint contents stay inside private owned runtime storage; copying explicitly excludes this checkpoint directory. They are removed only after their owning application stops. If stopping cannot be confirmed, the script retains them for the wrapper's container-first cleanup or later journal recovery. The wrapper then cleans recorded containers, networks and runtime data. Qualification records must identify the script hash and actual result paths, and distinguish fixture failures from product failures.

The checkpoint ownership tests use temporary files and no deployment:

```bash
uv run --project backend python -W error::ResourceWarning -m unittest discover \
  -s e2e/scripts -p 'test_*.py'
```
