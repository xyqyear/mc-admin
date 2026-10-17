## Why

Default log parsing misses goal/challenge announcements and ANSI-wrapped
achievement text, while unanchored chat matching treats diagnostic fragments as
player messages. Historical logs also establish login and stopping variants that
must survive tighter message boundaries.

## What Changes

- Recognize task, goal, challenge and legacy achievement announcements, preserving
  display text and nested title brackets while consuming boundary ANSI SGR codes.
- Anchor chat, login and stopping defaults to structured log headers and known
  message bodies, including nested logger brackets and observed Sponge variants.
- Keep UUID and departure defaults unchanged, preserve capture-group contracts
  and event precedence, and leave explicitly saved scalar/list settings intact.
- Add anonymous behavior regressions and deployed API coverage for the resulting
  player history and session behavior.
- Non-goals: whitespace account names, Mod-specific milestone events, generalized
  ANSI normalization, parser event-model changes and saved-config migrations.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `log-parser-configuration`: define default achievement, chat, login and stopping
  recognition and preserve all explicitly saved parser values across upgrades.

## Impact

Backend default configuration and behavior tests, deployed player API E2E cases,
the existing log-monitor topic and coverage documentation are affected. Public
API schemas, frontend code, database schema and Docker behavior remain unchanged.
There are no new dependencies or breaking configuration/data changes; existing
installations retain saved rules until an administrator explicitly adopts defaults.
