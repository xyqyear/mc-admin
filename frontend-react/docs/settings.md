# Application settings

`features/settings` owns the runtime settings pages under `/settings/*`.
The application sidebar provides a system-settings submenu with direct links to
DNS, snapshots, log parsing, players, map rendering, world and self-check pages.
Each page defines its own field groups and controls. DNS operational status and
manual synchronization remain in the separate DNS management feature.

## Contracts and transport

`contracts.ts` declares the complete resource types. `api.ts` exposes a typed
read/replace/reset resource for each `/api/settings/<resource>` path; hyphenated
paths are used for `log-parser` and `self-check`. GET, PUT and POST-reset return
the effective configuration directly. PUT submits the complete resource.
Backend validation and storage are described in
[runtime configuration](../../backend/docs/dynamic-config.md).

Settings field changes are implemented together in the backend contracts,
defaults and save validation, frontend contracts and page, and behavior tests.
Adding a page also updates application routes, public screen entries and sidebar
navigation.

## Editing and controls

`ui/SettingsEditor.tsx` owns read/retry, resource-scoped drafts, comparison,
confirmed reload/reset and saving. Failed initial reads never establish an empty
writable editor. Background reads preserve authored content. Reload discards
content only after a successful read; failed saves retain the draft. Successful
saves and resets accept the effective response values.

Pages use the controls in `shared/components/FormFields.tsx`. Numeric inputs
preserve zero and distinguish empty input. List editors support explicit item
addition/removal and optional ordering. Map editing rejects empty or duplicate
keys before submission. Parser rules use textareas; the player Query command uses
Monaco. DNS provider branches and manual addresses are authored in the DNS page.

## Effects and verification

Commands update the settings query and invalidate dependent snapshot, DNS or
self-check reads. DNS saving invokes its own synchronization command and reports
configuration persistence separately from synchronization failure.

`SettingsScreens.integration.test.tsx` exercises the real controls and HTTP
boundary, including comparison, failed reads/writes, reset, provider switching,
maps, lists and command editing. The browser settings journeys verify actual
sidebar navigation and deployed saves. Related API scenarios are listed in the
[system coverage inventory](../../e2e/docs/coverage/system.md).
