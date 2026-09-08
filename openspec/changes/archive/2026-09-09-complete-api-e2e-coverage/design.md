## Context

See proposal.md. The implementation builds on `e2e/docs/architecture.md` and the full inventory in `e2e/docs/coverage.md`. Domain contracts are in `backend/docs/`, particularly auth, cron, self-check, files/archive-upload, templates/servers, player identity/log-monitor, server-map, world-restore, chunk-prune, snapshots and DNS.

## Goals / Non-Goals

**Goals:** Complete the backend feature-family regression catalog, make operation coverage auditable, keep fixtures owned and independently reproducible, and validate real effects. Repair narrowly scoped defects exposed by those assertions.

**Non-Goals:** Browser interaction coverage, exhaustive combinations of every input and OS, a replacement testing DSL, production-attached tests or pretending unavailable cloud qualification ran.

## Decisions

- Split scenario implementation by domain while preserving the small existing engine. Public-format logs, usercache, NBT, Anvil and SNBT fixtures exercise actual deployed parsers and dependency binaries; fixture preparation does not import backend service functions.
- Use fresh isolation for mutation-heavy regressions. A World recipe combines the existing running server and private Restic providers, preserving slot ownership and cleanup.
- Extend common streaming transport for domain terminal discriminators and event observers; expose session-aware duplex WebSocket connections without duplicating authentication handling in domains.
- Use operational migration commands and explicit legacy database fixtures only when testing migration/cleanup input states that public APIs cannot create. All behavioral assertions use APIs or externally observable deployment outputs.
- Separate local regression tags from external DNS/provider qualification. External input files contain test credentials; namespace generated records per environment and register compensation immediately.
- Build API coverage from public schema and actual per-case evidence, retaining missing operations and status classes. Pair this route accounting with a feature matrix so mere route visitation is not mistaken for behavioral verification.
- CI audits complete case/shard results and requires observations for all deployed API operations in the full regression selection; filtered smoke/external selections only require their selected cases. These are separate gates so an unavailable cloud success path remains visible without silently skipping its configured external case.
- A failed documented contract drives a focused product regression and minimal fix, followed by rebuilding the production image and rerunning affected real scenarios. Update scoped CLAUDE/design docs for any resulting conventions.
- Task-center permission scenarios check every operation with anonymous, invalid-session and authenticated clients, and verify rejected mutations preserve task state. Route visitation alone does not establish authentication coverage.
- Audit credential matching separates configurable substring and exact-name rules. Actual login-code and completion-ticket flows are checked against audit and application logs. Metadata fixtures follow the supported format; parsing tests do not establish Minecraft loader compatibility.
- The production image uses Uvicorn INFO logging so WebSocket protocol DEBUG frames do not disclose login credentials. Credential checks include truncated ticket fragments because protocol diagnostics can abbreviate long frame payloads.
- Keep directory confinement, protect the managed data root and prevalidate multipart destinations before writing. These are explicit operation policies, not separately reproduced security findings; Linux backslashes remain legal filename characters. An already-absent mc-router route satisfies deletion, while other HTTP failures remain errors.
- Preserve equals signs inside Docker label values in the shared Docker/Compose parser. The lifecycle scenario saves such a label through the API and verifies real health and restart behavior using the configured Minecraft dependency.
- Pin Ruff for repeatable backend lint checks in development and CI. Preserve Pydantic model configuration, API dependency injection, cancellation boundaries and timestamp representations during lint cleanup; lint findings are not automatically behavioral defects.
- Qualification records distinguish deployed API evidence, real dependency integration, isolated original-code reproductions, deliberate policy changes and unresolved product semantics. Empty DNS target behavior remains unchanged until explicit empty state can be distinguished from unavailable target data.

## Risks / Trade-offs

- Real world rendering and Minecraft startup are costly → deterministic small assets, bounded slots, independent shards and explicit heavy-case timeouts.
- Logs and generated assets are inputs rather than real player accounts → state this boundary; retain actual Minecraft/RCON tests and separately qualify live profile fetching.
- Cloud credentials may be unavailable → complete configured scenarios and surface unexecuted external qualification; never substitute a fake cloud service.
- More tests expose unrelated defects → scope each fix to the failing observable contract, preserve targeted backend tests and avoid broad refactoring.
- Route counts alone overstate coverage → retain per-feature assertions and document remaining boundary combinations.
