## Context

See the proposal for the failure. The parser reads dynamic rules on every line;
`backend/docs/log-monitor.md` owns its ordered event matching and dispatch.
`backend/docs/dynamic-config.md` owns saved-value loading and schema defaults.

## Goals / Non-Goals

The change tightens the default leave pattern while retaining two capture groups.
Whitespace names, migration of stored values and the default-diff UI are outside
this implementation. The UI is tracked by #179, blocked by #143.

## Decisions

- Consume only bracketed log headers and match the message immediately after
  their separator. Reject address punctuation and a bare IPv4 subject.
- Keep explicit values under administrator control. Do not add a data migration,
  model validator or load-time replacement of the old default.
- Retain existing parser and player-service contracts, including genuine leave
  observations without a preceding join. A session-existence filter would change
  that recovery behavior and still mishandle a same-name failed connection.
- Reuse existing parser tests and deployed player-log scenario for focused
  coverage; add no new fixture framework or external identity requests.

## Risks / Trade-offs

- Existing installations can retain the old default → document explicit adoption
  by preserving the current module values and editing only its leave field.
- Special log formats and whitespace names are rejected → state the supported
  default format and retain administrator-customizable rules.

## Migration Plan

No stored-value or database migration. New/missing values use the new default;
saved values and custom rules load as before. Rolling back application code does
not rewrite administrator configuration. Update the two owning backend topics
and API E2E coverage; no AGENTS.md changes are needed.
