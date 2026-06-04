# Player Locations Overlay (`components/world-restore/players/`)

The world-restore page shows saved player positions from mcmap as both a
sidebar tab and a translucent Leaflet overlay. Locations are last-saved player
file positions, not live online positions.

## Data Flow

```
useWorldRestorePlayerLocations(serverId, mapInitialized)
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
event also primes the matching TanStack Query cache entry keyed by normalized
UUID.

## Sidebar

`PlayerLocationList.tsx` is the `玩家位置` tab in
`ServerWorldRestore.tsx`. It shows:

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

## Map Overlay

`usePlayersOverlay.ts` always registers a lightweight overlay while the map is
initialized, even when the visible player layer is toggled off. That keeps a
`L.Map` reference available so sidebar row clicks can pan without requiring the
visible overlay to be on.

`PlayerOverlayLayer.ts` filters to the current `region_dir_relpath` and renders
one non-interactive `L.divIcon` marker per visible player. The marker contains a
small pixelated avatar or placeholder plus a compact name pill. Online/offline
state is shown with a small dot on the avatar; offline markers are more
transparent. CSS in `players.css` sets `pointer-events: none` and partial
opacity so markers do not block map panning, selection, hover frames, or block
inspection.

## Cross-Dimension Pan

Player rows reuse the world-restore page's pending-pan ref used by FTB claims.
For off-dimension rows, the page stores the target relpath and X/Z block
position, switches dimension via the URL, then consumes the pending pan during
the next overlay render before Leaflet layers are attached. This preserves the
same StrictMode-safe, pan-before-add ordering as the FTB claims overlay.
