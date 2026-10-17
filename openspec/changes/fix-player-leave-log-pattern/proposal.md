## Why

The default departure pattern captures connection addresses as player names,
causing unnecessary identity lookups and confusing connection attempts with
players leaving. Historical corpus analysis confirmed 2,802 address captures.

## What Changes

- Restrict the default leave rule to structured log headers and a single player
  name, preserving the name/reason capture contract and rejecting address forms.
- Preserve every explicitly stored dynamic configuration value, including the
  previous default; new installations and missing values use the new default.
- Add focused parser and deployed log-observation regression coverage.
- Track opt-in comparison and adoption of newer defaults in issue #179, blocked
  by #143. This change does not implement that UI or support whitespace names.

## Capabilities

### New Capabilities

- `log-parser-configuration`: Default departure recognition and preservation of
  saved log-parser configuration when defaults change.

### Modified Capabilities

None.

## Impact

Backend log-parser defaults, focused tests, player API E2E and owning docs change.
Existing player services, public API schemas, database schema, persisted values,
frontend and Docker behavior retain their current contracts. Fixes #177.
