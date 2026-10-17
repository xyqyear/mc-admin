## Context

See [proposal](proposal.md) for motivation. The ordered parser and its side effects
are documented in [log monitoring](../../../backend/docs/log-monitor.md);
[dynamic configuration](../../../backend/docs/dynamic-config.md) owns default
filling and explicitly stored values. Historical research covered 15,658 files,
36,553,196,282 expanded bytes and 251,088,263 physical lines, without content hashes.
Anonymous regressions represent those formats; private raw logs remain outside Git.

## Goals / Non-Goals

**Goals:** Adopt the already replayed default combination, keep capture contracts
and first-match precedence, and verify player history/session effects through
existing test boundaries.

**Non-Goals:** Change parser inputs or event models, introduce new dependencies,
rewrite identity attribution, infer complete in-game achievement state, or migrate
stored settings. Scope is the four defaults named in the proposal.

## Decisions

- Build default strings from shared noncapturing bracket-header, name and SGR
  fragments. One nested header level covers the observed logger form; flat
  headers lose valid chat, while unrestricted bracket matching obscures message
  boundaries. Saved custom rules continue matching the original full line.
- Join/chat/achievement/stopping use the exact researched message forms. UUID
  and departure defaults stay byte-for-byte unchanged. Preserve the optional
  chat marker group, complete achievement display text and the two achievement
  fields instead of applying one account-name grammar to every event.
- Consume SGR only around achievement fields, excluding ESC from captured text.
  Global stripping would also change custom rules and earlier event fields;
  accepting arbitrary internal escape sequences risks polluted persisted titles.
- Retain explicit Sponge and Paper branches. Exact ordinary-only matching loses
  valid historical observations. Joined/left broadcasts remain outside parsing
  because database session reuse does not suppress all duplicate side effects.
- Keep current save/load semantics: no database-schema or rule-replacement
  migration, and no replacement of explicitly stored lists or scalars, even when
  equal to an older default. Existing schema-on-read handling may revalidate and
  reserialize stored settings without changing those explicit values.

## Risks / Trade-offs

- Historical copies contain overlapping observations → report parser counts, not
  unique awards or database mutations. The approved combination added 14,018
  achievement matches and removed 3,492 diagnostic chat nominations; four old
  achievement display fields became complete rather than trailing tokens.
- New logger formats, internal ANSI coloring and Mod milestones remain outside
  known defaults → retain administrator-owned full-line custom rules.
- Stopping closes sessions → assert chat/diagnostic negatives and all three known
  bodies, not merely successful regex matching.

## Migration Plan

Deploy new defaults for missing settings; existing stored values remain intact.
Administrators can explicitly adopt new rules using the current save flow.
Rollback restores earlier code defaults without rewriting saved values. Update
the log-monitor topic, behavior specification and E2E coverage owner; no AGENTS.md
or frontend structural changes are required. There are no CLAUDE.md files.
