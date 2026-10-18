## Context

The [UI conventions](../../../frontend-react/docs/ui-conventions.md) distinguish
generated Base UI components from application composition. The
[file-management topic](../../../frontend-react/docs/file-management.md) owns
`path`, `q`, and `regex` navigation; editor state is local and has no URL deep link.
[Browser verification](../../../frontend-react/docs/browser-tests.md) owns real
link behavior and isolated deployed fixtures.

## Goals / Non-Goals

**Goals:** Native link behavior across fixed destinations, one search destination
calculation, and unchanged source-page state on new-tab actions.

**Non-Goals:** Backend changes, editor-state persistence, replacement of action
flows or history-back, mobile drawer changes, or generated-source edits.

## Decisions

- Use React Router links with actual hrefs. Sidebar consumers use their existing
  `render` composition. Ordinary styled navigation uses anchor styling rather than
  Base UI Button, which enforces button semantics. Small presentation reuse is
  allowed; no new navigation framework is needed.
- Keep sidebar active matching and pathname-driven expansion. Group actions stay
  buttons. Native new-tab interactions do not call source-route navigation or
  mutate sidebar state.
- Build file destinations with URLSearchParams and captured search-root/result
  metadata. Share the calculation between existing ordinary navigation and hrefs.
  Preserve file literal filters, directory clearing and structural-parent regex.
- File breadcrumbs, parent-directory controls and directory names share the same
  path destination builder. Ordinary clicks retain filter/selection cleanup;
  native new-tab actions leave the source selection intact. Error recovery links
  retain full-document navigation.
- Intercept only an unmodified primary self-target click where the existing tree
  callback is required. It performs ordinary navigation once. Other clicks retain
  native defaults. Checkbox, expander, name and explicit new-tab icon are siblings.
- Explicit new-tab icons use isolated opener attributes. Newly opened pages pass
  through the existing session/route guards; no credentials are copied into URLs.

## Risks / Trade-offs

- Button-to-link semantic changes affect test selectors → update only navigation
  expectations and verify actions remain buttons.
- Double navigation or source dialog reset → guard ordinary-click callbacks and
  assert source URL, selection, draft and expansion after native popup actions.
- Filename punctuation and stale drafts → test URL parsing using independent
  expected paths and the captured result criteria.
- Structural parents are not actual batch results → preserve current selection
  aggregation and layout regressions.

## Migration Plan

No dependencies, API or persistence migration is required. Update existing UI,
file and browser topics plus the behavior specification. No agent-instruction or
CLAUDE.md structural updates are needed. Rollback restores frontend navigation
presentation while preserving the same existing destination URLs.
