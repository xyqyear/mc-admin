## Why

Navigation implemented only through click handlers cannot use the browser's
middle-click, modified-click or link context-menu behavior. Issue #140 identifies
sidebar entries and advanced-search results as the main affected workflows.

## What Changes

- Give fixed-destination navigation real links while preserving current-page
  routing, appearance, active state and permission gates.
- Make advanced-search names navigable links and add an explicit new-tab icon.
  Reuse the captured result destination for normal and new-tab navigation.
- Keep the source tab's search, selection and expansion state during new-tab
  navigation; retain directory toggles and batch controls as separate actions.
- Convert other fixed navigation entries consistently, retaining mutation,
  authentication, logout and history-back flows as actions.
- Non-goals: file-editor deep links, automatic downloads, new mobile-close
  behavior, backend APIs, persisted settings or dependency changes.

## Capabilities

### New Capabilities

- `native-navigation-links`: native browser navigation from application entries
  and search results without unwanted source-page side effects.

### Modified Capabilities

None.

## Impact

Frontend sidebar, file-search navigation, fixed-route action presentation and
targeted component/browser tests are affected. Generated UI sources remain under
official CLI management. Browser coverage and owning UI/file documentation will
describe the contract. Backend APIs, authentication, persistence and Docker
behavior are unchanged; no migrations or breaking data changes are introduced.
