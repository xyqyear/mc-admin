# Configuration editors and drafts

`features/configuration` owns editing existing-server Compose, template parameters
and mode conversions. `pages/server/servers/ServerCompose.tsx` is the route adapter.
Global template definitions/defaults belong to [templates](templates.md), while
the backend [configuration application](../../backend/docs/configuration.md)
owns version checks, source metadata and staged writes.

## Contracts and requests

`features/configuration/contracts.ts` and `api.ts` own Compose reads/writes, template snapshot parameters, previews and both mode conversions. `queries.ts` exposes shared query options; read-only template-copy selection uses the same versioned Compose cache with a string selector. `commands.ts` requires an accepted version for every configuration write and only announces task/operation discovery after submission.

## Editor drafts

The configuration feature models an accepted baseline (including an opaque version), a local draft and current remote data separately. Untouched Compose/template editors follow fresh remote reads, including a page reopened from cached data after an independent task. Once the user authors content, accepts a comparison, or receives an applied submission, background reads cannot replace that draft. Edited template forms retain their accepted schema until explicit comparison. A remote mode change preserves the original editor until the user confirms discarding its draft and loading the new mode.

Conversion dialogs keep their captured baseline even while the text session appears untouched: selected templates, extracted variables and authored form values live outside that session. A background Compose refresh therefore still requires comparison before submitting conversion parameters. The untouched-read policy is an explicit opt-in for the Compose and template editors, not a default for every configuration flow.

Every configuration write submits the baseline version. HTTP 409 `configuration_conflict` or a background task's matching `error_code` requires a successful remote read and full baseline/remote/draft comparison. “接受此版本为新基准” preserves the draft, accepts only the displayed version, and returns to editing; a separate submit performs the write. Successful tasks return the actual applied `version`: the session accepts that submitted snapshot as its baseline while preserving any newer local draft. Already-read data from before completion is not treated as a new conflict; a fresh read with any other version still requires comparison. A further race remains a conflict. Confirmed reload is the explicit discard action and only resets after a successful read. Mode conversion preserves edited variables during conflicts and reruns the comparison after acceptance. Drafts remain local to mounted editors.

File, global template/default-variable and dynamic-config editors use `useEditorDraft` with a resource key. Remote updates replace pristine content but preserve authored content. Loading failures never establish a writable empty session; a successful empty read is valid content. Their existing write contracts are unchanged.

## Completion and validation

`configuration_conflict` preserves authored data and requires explicit comparison
before accepting a new baseline. An accepted version is not an automatic retry;
the user submits again. Background task and cross-page refresh follow
[operation completion](operation-refresh.md). Real editor integration tests keep
the query/mutation hooks and vary HTTP behavior, as described in [testing](testing.md).
