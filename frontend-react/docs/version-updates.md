# Version Update Notifications

When the bundled frontend version is newer than the version recorded in localStorage, a modal surfaces the changelog the first time the user lands. Manually maintained — no remote check, no API call. The list of versions and their changes lives in `src/app/version/config.ts`.

## Why a manual list

A self-hosted app doesn't have a meaningful "latest available" remote endpoint to query — the user already pulled the new image / built the new bundle. The notification's job is to tell them what changed in *this* bundle they're now running, drawn from a list the maintainer keeps in source. No update mechanism, no auto-fetch, no telemetry.

## Detection flow

`app/version/useVersionCheck.ts`:

1. On mount, after a 1 s debounce (avoids interfering with login redirect), reads `localStorage["mc-admin-last-seen-version"]`.
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

## Editing `app/version/config.ts`

To ship a new version's notification:

```ts
export const versionUpdates: VersionUpdate[] = [
  // … earlier releases …
  {
    version: '3.0.2',
    date: '2026-05-10',
    title: '恢复与地图体验优化',
    description: '完善范围恢复和地图刷新。',
    features: ['Selective world rollback at chunk level (#456)'],
    fixes: ['Map tile cache invalidation across dimensions (#492)'],
    improvements: ['Faster mcmap palette generation for modded servers'],
  },
];
```

Append each release to the list. `currentVersion` is the greatest version under `compareVersions`, independent of list position; the dialog sorts matching entries newest-first.

Comparison follows SemVer precedence: numeric major/minor/patch, followed by dot-separated prerelease identifiers. Numeric identifiers compare numerically and precede non-numeric identifiers; final releases follow their prereleases (`6.0.0-beta.1 < 6.0.0-beta.2 < 6.0.0`). Build metadata after `+` does not affect ordering. Existing stored versions may omit minor/patch or include a `v` prefix. An empty or malformed stored version compares as `0.0.0`, so it cannot break the notification UI. Release entries use complete `major.minor.patch` versions, with optional prerelease/build suffixes.

## Files

- `src/app/version/config.ts` — version list + comparator
- `src/app/version/useVersionCheck.ts` — detection hook
- `src/app/version/VersionUpdateDialog.tsx` — modal UI
- `src/app/version/issueParser.tsx` — `#123` → GitHub link
