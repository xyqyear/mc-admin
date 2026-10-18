# Frontend targeted testing

This guide owns unit/query integration verification. [Browser tests](browser-tests.md)
exercise the built app in an owned real deployment. Root [delivery rules](../../AGENTS.md#交付与测试要求)
require complete remote qualification of the latest commit; local execution
selects only changed behavior and affected call paths.

## Commands and selection

From `frontend-react/`, choose actual related test files and optional case names:

```bash
pnpm exec vitest run src/features/backups/preview.integration.test.tsx
pnpm exec vitest run <related-file> -t '<related test name>'
```

`pnpm test` runs the complete architecture suite before Vitest, so passing it a
file does not make it a targeted local command. `pnpm test:architecture` and
unfiltered `pnpm test:browser` are also full-suite CI entry points. Related
architecture cases require explicit test-name selection. Do not reconstruct a
full suite through batches or agents. Documentation-only edits need no local tests.

Keep lint, TypeScript, import-boundary and build checks appropriate to code
changes. Generated-contract validation needs backend uv dependencies; see
[data contracts](data-architecture.md#generated-contracts). The Static Checks
workflow records individual Vitest timings and runs bundling separately from
TypeScript diagnostics.

## Observable assertions

Use real query hooks and isolated QueryClients around HTTP boundaries. Wait for
observer-driven cache/UI effects with `waitFor`; a completed refetch alone does
not establish that React effects ran. Keep deterministic expected bytes, error
feedback and unchanged-state assertions independent of production algorithms.

For cancellation, observe an accepted cancellation while the real task remains
running before asserting its terminal outcome. Profile tests assert the cached
name and cache update before rerender. For workflows migrating to tasks, verify
acceptance is not completion, duplicate submissions, reconnect, explicit
cancellation, shutdown and owned cleanup.

## HTTP/query integration tests

`src/test/http.ts` creates isolated real QueryClients and Axios-adapter responses; `TestProviders.tsx` supplies the client and router. Existing page tests preserve real query/mutation hooks while replacing transport and heavyweight editors. Query retry tests verify actual attempt counts.

`features/configuration/ConfigurationScreen.test.tsx` and `app/operations/OperationObserver.test.tsx` use MSW HTTP handlers with real QueryClients. They exercise delayed loads, intentional empty writes, draft preservation, synchronous/async conflicts, explicit acceptance and resubmission, mode conversion, leaving/returning to the page, incremental deduplication, paginated reconnection, explicit resets and remounted session isolation. `App.test.tsx` exercises production AUTH-event and HTTP-401 cache cleanup, login cache/navigation, new-owner resource reads and cancellation of late old-session observation. Query hooks and invalidation remain real.

Archive upload integration keeps native File/Blob bytes, the real SHA256
implementation and the real task waiter. A fixed `abc` digest independently
checks verification; unequal bytes and missing digests reject publication and
clean up the session. Running tasks at 100% and temporary status-read failures
remain pending until a successful terminal outcome. Lifecycle unit tests retain
controlled transport and hashing for queue, pause, retry, unmount and close
boundaries.

The Node/WASM upload fixture installs its JSDOM globals with `vi.hoisted` before
importing QueryClient providers. This keeps query observation in browser mode,
including interval-based recovery after a failed task read.

## Workflow regression owners

The tests use real QueryClient caches and MSW HTTP boundaries. Coverage includes file filtering/drafts/partial batches, prune availability and late rejection, shared world URL selection, task disconnection/reconnection, accepted cancellation while observation still reports running, ready-preview disposal, old-generation history guards and off-page partial-write completion. Server controls retain their status-specific availability and stay blocked by an active task until the maintenance projection clears.

`app/overview/queries.integration.test.tsx` verifies cross-page fresh-cache reuse, shared invalidation and stopped-server gating through real MSW endpoints. Player integration tests verify initial cached names, shared-cache updates before rerender, stable map identities under UUID normalization, and streamed updates reaching both single-profile and map observers. Schedule integration tests keep active-but-unregistered jobs visible, retry registration, refresh the server card and read older responses without the optional fields.

DNS integration tests exercise degraded/unknown and empty desired states, update availability, visible partial provider writes after an overall failure, and refresh failures without false success feedback.

Browser transport faults may delay or reject delivery, but backend versions,
task outcomes and data effects remain real. Test coverage details and owned
cleanup requirements belong to [browser verification](browser-tests.md).
