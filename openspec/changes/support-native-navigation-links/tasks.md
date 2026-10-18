## 1. Native destinations

- [x] 1.1 Convert sidebar destinations to links while preserving active state, permissions and operation buttons; add targeted regressions.
- [x] 1.2 Share captured file-search destinations between normal navigation and native links, add explicit new-tab links and preserve tree selection/expansion; add targeted regressions.
- [x] 1.3 Convert other fixed-destination entries to styled links without changing mutation, authentication, logout or history-back actions; add affected regressions.
- [x] 1.4 Expose native breadcrumb, parent-directory and directory-name links while retaining filter/selection cleanup on ordinary navigation and full-document error recovery.

## 2. Browser behavior and contracts

- [x] 2.1 Add owned real-browser verification for native sidebar/search new tabs, encoded destinations and source-page state; update affected navigation selectors.
- [x] 2.2 Update owning UI/file/browser documentation and sync the new behavior specification.

## 3. Verification

- [x] 3.1 Pass explicitly selected component/integration/browser regressions, required frontend static/contract/build checks and independent diff review.

Local evidence: 33 selected Vitest cases and five related owned Chromium journeys
passed; lint/import boundaries, TypeScript, API contract freshness, application
build and strict change/spec validation passed. The final browser run used the
backup recipe, retained all source-state assertions and completed owned cleanup.
Independent reviews covered native link semantics, navigation wiring and affected
test selectors.

Delivery requires committing and pushing the implementation branch and complete
qualification of its exact latest SHA with `publish=false`; report that gate
separately from implementation-task completion.
