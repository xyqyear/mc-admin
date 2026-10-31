# Version Update Notifications

When the bundled frontend version is newer than the version recorded in localStorage, a modal surfaces the changelog the first time the user lands. Manually maintained data lives in `public/static/release.json`, served by the same image at `/static/release.json`. There is no external update service or API call.

## Why a manual list

A self-hosted app doesn't have a meaningful "latest available" remote endpoint to query — the user already pulled the new image / built the new bundle. The notification's job is to tell them what changed in *this* bundle they're now running, drawn from a list the maintainer keeps in source. No update mechanism, no auto-fetch, no telemetry.

## Detection flow

`app/version/useVersionCheck.ts`:

1. Once valid release data is loaded, after a 1 s debounce (avoids interfering with login redirect), reads `localStorage["mc-admin-last-seen-version"]`.
2. If the key is missing → first visit. Persists the current version, no modal.
3. If the stored version is older than `currentVersion` → upgrade. Sets `shouldShowDialog = true` unless a "remind later" timestamp is still active (1 hour after the user clicked Remind Later).
4. Returns `{ shouldShowDialog, fromVersion, toVersion, handleClose, handleRemindLater }`.

`handleClose()` updates the stored version to the current one — the modal won't reopen until the next upgrade.
`handleRemindLater()` writes a timestamp to localStorage; the version key stays unchanged so the modal reappears in 1 hour.

## Modal content

`VersionUpdateDialog.tsx` renders every version entry between `fromVersion` and `toVersion` (inclusive of `toVersion`):

- Version header
- **Features** (✨), **Fixes** (🐛), **Improvements** (⚡) — three sections with bullet lists
- Issue references like `#123` are converted to GitHub links via `app/version/issueParser.tsx`

Two buttons: Close (mark as seen), Remind Later (1-hour snooze).

## Loading and editing release data

`releaseData.ts` uses the shared QueryClient with `cache: no-store`, infinite in-memory freshness and explicit retry on error. Unavailable or invalid data never writes acknowledgment state; the dialog offers retry. Navigation remains usable while loading.

Append objects to `public/static/release.json`. Required string fields are `version`, `date`, `title` and `description`; optional `features`, `fixes` and `improvements` are string arrays. Use unique complete SemVer versions without build metadata and ISO dates. Comparison, URL and rendering logic stays in TypeScript. The tag must match the greatest version.

Metadata-only changes reuse business qualification and receive data validation plus final-image notification smoke verification. See [release qualification](../../docs/release.md).

Append each release to the list. `currentVersion` is the greatest version under `compareVersions`, independent of list position; the dialog sorts matching entries newest-first.

Comparison follows SemVer precedence: numeric major/minor/patch, followed by dot-separated prerelease identifiers. Numeric identifiers compare numerically and precede non-numeric identifiers; final releases follow their prereleases (`6.0.0-beta.1 < 6.0.0-beta.2 < 6.0.0`). Build metadata after `+` does not affect ordering. Existing stored versions may omit minor/patch or include a `v` prefix. An empty or malformed stored version compares as `0.0.0`, so it cannot break the notification UI. Release entries use complete versions with optional prerelease identifiers; stored-version comparison still tolerates build metadata.

## Files

- `public/static/release.json` — deployed entries
- `src/app/version/config.ts` — comparator and issue URLs
- `src/app/version/releaseData.ts` — validated loading and query policy
- `src/app/version/useVersionCheck.ts` — detection hook
- `src/app/version/VersionUpdateDialog.tsx` — modal UI
- `src/app/version/issueParser.tsx` — `#123` → GitHub link
