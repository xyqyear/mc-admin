# Player Locations Overlay (`features/world/layers/players/`)

The restore and prune pages show saved player positions from mcmap as both a
sidebar tab and a translucent Leaflet overlay. Locations are last-saved player
file positions, not live online positions.

## Data Flow

```
useWorldPlayerLocations(serverId, mapInitialized)
        |
        v
PlayerLocationsResponse.players[] --> usePlayerMapProfiles(uuids) --> POST /players/profiles/stream
        |                                      |
        |                                      v
        +--------------> PlayerLocationList <-- PlayerMapProfileResponse
        |
        +--------------> usePlayersOverlay --> ServerMap overlays[]

useServerOnlinePlayers(serverId) ---> normalized online UUID set
        |                                      |
        +--------------> PlayerLocationList   +--> usePlayersOverlay
```

Location extraction is one request for the server/world. Profile resolution is
one SSE request for the normalized UUID set, deduplicated by
`usePlayerMapProfiles`. The stream emits cached profiles immediately, then
fills in missing names and avatars as Mojang lookups complete. Each profile
event writes the matching TanStack Query cache entry keyed by normalized
UUID. Map and individual-profile consumers observe that same entry; disabling the stream does not detach cache updates. Stream progress/error remains local, without a second mutable profile store.

`features/players/identity.ts` supplies the public pure `normalizeUuid()` helper
used by profile queries, the world controller, the list and marker layers. It
removes hyphens, lowercases exactly 32 hexadecimal characters and returns `null`
for missing or invalid values. UUID syntax normalization does not impose an
online-mode version check. Location identity uses `uuid ?? id`; an explicitly
empty or invalid UUID stays unresolved rather than falling back to a different
ID. Online filtering and profile-cache lookup use this same normalized identity.

Profile events validate the concrete wire fields before entering the cache.
Nullable profile fields are always present, with JSON `null` for unavailable
values. An unresolved player keeps its own UUID fallback while other players'
names and avatars load normally, including on a first visit without cached data.
The finite stream ends with `complete` or `error`; EOF without either displays
a recoverable Chinese error in the player tab. Cached names, saved locations
and map controls remain usable. “重试玩家资料” starts a new profile stream for
the same UUID set without refetching positions. Disabling or unmounting aborts
the request without reporting an error. The shared reader skips malformed JSON;
decoded event-handler failures end dispatch and release the reader.

## Sidebar

`WorldPlayerLocationList.tsx` binds the common controller's `players` group and
the current map dimension to `PlayerLocationList.tsx`. Both
`WorldRestoreScreen.tsx` and `ChunkPruneScreen.tsx` compose this `玩家位置` tab.
It shows:

- a Switch for overlay visibility,
- a Switch for filtering the list and map to online players only,
- current-dimension count vs total player locations,
- online player-location count vs total player locations,
- skipped-file count when mcmap reports malformed or incomplete files,
- avatar placeholder or cached Mojang avatar,
- online/offline state when the server online-player query is available,
- resolved player name or UUID fallback,
- dimension label and X/Y/Z coordinates.

Online players sort before offline players. Rows in the current dimension are
fully opaque. Rows in other matched dimensions are dimmed but clickable;
clicking switches the URL `#dim=` and pans after the new map render. Rows whose
mcmap dimension cannot be resolved to a region directory stay visible as
unmatched and are not clickable.

Sorting computes identity, online status, dimension priority and display name
once per location, and reuses an `Intl.Collator` for case-insensitive name
comparison. Memoized rows retain their render when their own profile and
presentation inputs are unchanged. Native `content-visibility: auto` skips layout
and paint for rows outside the scroll viewport, with a 65px intrinsic row size.
All rows remain in the document for browser search, keyboard navigation and
cross-dimension positioning.

## Map Overlay

`usePlayersOverlay.ts` always registers a lightweight overlay while the map is
initialized, even when the visible player layer is toggled off. That keeps a
`L.Map` reference available so sidebar row clicks can pan without requiring the
visible overlay to be on.

`PlayerOverlayLayer.ts` filters to the current `region_dir_relpath` and online
setting, then draws visible player markers onto one Canvas in Leaflet's marker
pane. Each marker retains its name pill, pixelated avatar or placeholder,
online/offline dot and status-dependent transparency. `playerMarkerSprite.ts`
rasterizes each marker at the device pixel ratio; unchanged markers reuse that
bitmap across redraws, including after leaving and re-entering the viewport.
Avatar images are shared by their base64
source, with a placeholder until decoding succeeds and after decoding fails.

The viewport includes a pan gutter and the full icon footprint, preserving
partially visible names and avatars. Ordinary dragging translates the cached
Canvas with the map pane, without repainting each player. Crossing the gutter,
zooming and resizing schedule one redraw per animation frame. Zoom animations
transform the Canvas before it redraws fixed-size markers for the final zoom.
There is no player cap, clustering or name suppression: zooming out still draws
every eligible location. Marker painting follows vertical map order so lower
players paint above higher players, matching Leaflet marker stacking.

Profile, position and status changes update render entries by
`playerLocationKey()` and invalidate only the affected marker bitmaps. The
Canvas exposes the eligible player count as an accessible image label; the
sidebar retains each player's full text and navigation. `players.css` keeps the
Canvas non-interactive so panning, selection, hover frames and block inspection
pass through it.

Bitmaps are created lazily when markers enter the viewport gutter, and retained
while their render entries remain eligible. Panning and position-only updates
reuse them; changes to a name, avatar, status or device pixel ratio release the
affected bitmaps. Filtering, dimension changes and removed locations release
entries that are no longer eligible. The cache holds at most one bitmap per
eligible location and grows with visited locations and the square of the device
pixel ratio; it has no separate byte budget or timer-based eviction.

Hiding the layer releases its pixel buffers and decoded images while retaining
the map reference for sidebar navigation. Hidden layers do not allocate a new
buffer when the map moves, zooms or resizes. Removing the layer also detaches map
listeners, cancels scheduled animation work and clears image callbacks, so late
avatar loads cannot redraw an unmounted layer. Reattachment rebuilds against
the current viewport.

## Cross-Dimension Pan

`useWorldMapController` owns one pending-pan ref shared by player rows and FTB
claims. An off-dimension row stores the target relpath and X/Z block position,
switches the URL dimension and clears the previous view coordinates. An overlay
render applies the pan only when its dimension matches the target, before
Leaflet layers attach. A microtask clears the ref so subsequent renders do not
replay the pan while StrictMode keeps the same pan-before-add ordering.

`mapConfig.blockToLatLng()` maps block X/Z to `[-Z, X]`, preserving negative
coordinates for markers and pan. Block-to-chunk and chunk-to-region conversions
use floor division, so negative positions retain their correct world cells.
