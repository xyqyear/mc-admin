import { usePlayerMapProfiles, useServerOnlinePlayers } from '@/features/players/queries'
import { useServerQueries } from '@/features/servers/queries'
import { readHashUrlParams, replaceHashUrlParams, useHashUrlParams, type HashUrlParamsUpdater } from '@/shared/hooks/useHashUrlParams'
import { queryKeys } from '@/shared/http/api'
import { useQueryClient } from '@tanstack/react-query'
import type L from 'leaflet'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FtbClusterEntry, FtbTeamEntry } from '@/features/world/layers/claims/contracts'
import { useClaimsOverlay } from '@/features/world/layers/claims/useClaimsOverlay'
import type { PlayerLocationEntry } from '@/features/world/layers/players/contracts'
import { normalizePlayerUuid } from '@/features/world/layers/players/playerLocationDisplay'
import { usePlayersOverlay } from '@/features/world/layers/players/usePlayersOverlay'
import type { ServerMapView } from '@/features/world/map/ServerMap'
import { buildDimensionOptions, relpathOf, selectWorldDimension } from '@/features/world/map/worldDimensions'
import { useFtbClaims, useMapRegions, useMapStatus, useWorldDimensionLabels, useWorldLayout, useWorldPlayerLocations } from '@/features/world/queries'

const STOPPED_STATUSES = new Set(['EXISTS', 'CREATED', 'REMOVED'])
const WORLD_MAP_REACTIVE_URL_KEYS = ['dim', 'mode'] as const
const WORLD_MAP_URL_KEYS = [
  ...WORLD_MAP_REACTIVE_URL_KEYS,
  'z',
  'cx',
  'cz',
] as const

function replaceWorldMapUrlParams(update: HashUrlParamsUpdater): void {
  replaceHashUrlParams(WORLD_MAP_URL_KEYS, update)
}

function parseInitialView(params: URLSearchParams): ServerMapView | undefined {
  if (!params.has('z') && !params.has('cx') && !params.has('cz')) return undefined
  const z = Number(params.get('z') ?? 0)
  const cx = Number(params.get('cx') ?? 0)
  const cz = Number(params.get('cz') ?? 0)
  return {
    zoom: Number.isFinite(z) ? z : 0,
    cx: Number.isFinite(cx) ? cx : 0,
    cz: Number.isFinite(cz) ? cz : 0,
  }
}

export const setWorldMapMode = (mode: string) => replaceWorldMapUrlParams((params) => params.set('mode', mode))

export function useWorldMapController(serverId: string) {
  const [urlParams] = useHashUrlParams(WORLD_MAP_REACTIVE_URL_KEYS)

  const dimensionRelpath = urlParams.get('dim') ?? null
  const rawMode = urlParams.get('mode')
  const [initialView] = useState(() =>
    parseInitialView(readHashUrlParams(WORLD_MAP_URL_KEYS)),
  )

  const layoutQ = useWorldLayout(serverId)
  const labelsQ = useWorldDimensionLabels(serverId)
  const { useServerStatus, useServerInfo } = useServerQueries()
  const statusQ = useServerStatus(serverId)
  const serverInfoQ = useServerInfo(serverId)
  const serverStopped = statusQ.data ? STOPPED_STATUSES.has(statusQ.data) : false

  const queryClient = useQueryClient()
  const mapStatusQ = useMapStatus(serverId)
  const mapInitialized =
    !!mapStatusQ.data?.client_jar_present &&
    !!mapStatusQ.data?.palette_present &&
    !!mapStatusQ.data?.palette_current
  const [initOpen, setInitOpen] = useState(false)
  const [initForce, setInitForce] = useState(false)
  const openInitDialog = useCallback((force = false) => {
    setInitForce(force)
    setInitOpen(true)
  }, [])
  const handleInitComplete = useCallback(() => {
    setInitOpen(false)
    setInitForce(false)
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])
  const handleInitClose = useCallback(() => {
    setInitOpen(false)
    setInitForce(false)
  }, [])

  const handleRefreshMap = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])

  const { rootList, currentDimension, currentRoot } = useMemo(
    () => selectWorldDimension(layoutQ.data, dimensionRelpath),
    [dimensionRelpath, layoutQ.data],
  )

  const regionRelpath = useMemo(() => {
    if (!currentDimension || !currentRoot) return null
    return relpathOf(currentDimension.region_dir, currentRoot.path)
  }, [currentDimension, currentRoot])

  // Seed default dim into URL once layout loads. Replace, no history entries.
  useEffect(() => {
    if (!currentRoot || !currentDimension) return
    const wantedRel = relpathOf(currentDimension.region_dir, currentRoot.path)
    if (dimensionRelpath === wantedRel) return
    replaceWorldMapUrlParams((params) => {
      params.set('dim', wantedRel)
    })
  }, [currentRoot, currentDimension, dimensionRelpath])

  const {
    data: regionsList,
    isLoading: regionsLoading,
    isError: regionsError,
  } = useMapRegions(
    serverId,
    mapInitialized ? regionRelpath ?? undefined : undefined,
  )

  const regionsMap = useMemo(() => {
    if (!regionsList) return undefined
    return new Map(regionsList.map(([x, z, mt]) => [`${x},${z}`, mt]))
  }, [regionsList])

  const handleViewChange = useCallback(
    (view: ServerMapView) => {
      replaceWorldMapUrlParams((params) => {
        params.set('z', String(view.zoom))
        params.set('cx', String(view.cx))
        params.set('cz', String(view.cz))
      })
    },
    [],
  )

  const handleDimensionChange = useCallback(
    (dimRelpath: string) => {
      replaceWorldMapUrlParams((params) => {
        params.set('dim', dimRelpath)
        // Different dimensions have different extents.
        params.delete('z')
        params.delete('cx')
        params.delete('cz')
      })
    },
    [],
  )


  const claimsQ = useFtbClaims(serverId, mapInitialized)
  const claimsAvailable = !!claimsQ.data?.available
  const [claimsOverlayVisible, setClaimsOverlayVisible] = useState(true)
  const teams = useMemo<FtbTeamEntry[]>(
    () => claimsQ.data?.teams ?? [],
    [claimsQ.data],
  )
  const pendingPanRef = useRef<{
    dimRelpath: string
    bx: number
    bz: number
  } | null>(null)

  // Cross-dim pan via overlay render; see docs/ftb-claims-overlay.md.
  const handleOverlayRender = useCallback(
    (map: L.Map, dim: string | null) => {
      const pending = pendingPanRef.current
      if (!pending || pending.dimRelpath !== dim) return
      queueMicrotask(() => {
        pendingPanRef.current = null
      })
      map.setView([-pending.bz, pending.bx], map.getZoom(), { animate: false })
    },
    [],
  )

  const {
    overlays: claimsOverlays,
    popover: claimsPopover,
    closePopover: closeClaimsPopover,
    highlightClusters,
    panToBlock,
  } = useClaimsOverlay({
    teams,
    currentDimRelpath: regionRelpath,
    enabled: claimsAvailable && claimsOverlayVisible,
    onRender: handleOverlayRender,
  })

  const handleRefreshClaims = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.ftbClaims.all })
  }, [queryClient])


  const playerLocationsQ = useWorldPlayerLocations(
    serverId,
    mapInitialized,
  )
  const [playersOverlayVisible, setPlayersOverlayVisible] = useState(true)
  const [onlinePlayersOnly, setOnlinePlayersOnly] = useState(false)
  const playerLocations = useMemo<PlayerLocationEntry[]>(
    () => playerLocationsQ.data?.players ?? [],
    [playerLocationsQ.data],
  )
  const onlinePlayersQ = useServerOnlinePlayers(serverId)
  const onlinePlayerUuids = useMemo(
    () =>
      new Set(
        (onlinePlayersQ.data ?? [])
          .map((player) => normalizePlayerUuid(player.uuid))
          .filter((uuid): uuid is string => !!uuid),
      ),
    [onlinePlayersQ.data],
  )
  const onlineStatusAvailable = !!onlinePlayersQ.data && !onlinePlayersQ.isError
  const playerUuids = useMemo(
    () =>
      playerLocations
        .map((player) => player.uuid)
        .filter((uuid): uuid is string => !!uuid),
    [playerLocations],
  )
  const playerProfiles = usePlayerMapProfiles(
    playerUuids,
    mapInitialized && !!playerLocationsQ.data,
  )
  const { overlays: playersOverlays, panToBlock: panToPlayerBlock } =
    usePlayersOverlay({
      players: playerLocations,
      currentDimRelpath: regionRelpath,
      profilesByUuid: playerProfiles.profilesByUuid,
      onlinePlayerUuids,
      onlineOnly: onlinePlayersOnly && onlineStatusAvailable,
      onlineStatusAvailable,
      enabled: mapInitialized,
      visible: playersOverlayVisible,
      onRender: handleOverlayRender,
    })

  const mapOverlays = useMemo(() => {
    const out = [...(claimsOverlays ?? []), ...(playersOverlays ?? [])]
    return out.length > 0 ? out : undefined
  }, [claimsOverlays, playersOverlays])

  const handleRefreshPlayers = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: queryKeys.worldRestore.playerLocations(serverId),
    })
  }, [queryClient, serverId])

  const handleClusterClick = useCallback(
    (cluster: FtbClusterEntry) => {
      if (cluster.region_dir_relpath === regionRelpath) {
        const [bx, bz] = cluster.centroid_block
        panToBlock(bx, bz)
        return
      }
      if (cluster.region_dir_relpath) {
        const [bx, bz] = cluster.centroid_block
        pendingPanRef.current = {
          dimRelpath: cluster.region_dir_relpath,
          bx,
          bz,
        }
        handleDimensionChange(cluster.region_dir_relpath)
      }
    },
    [regionRelpath, panToBlock, handleDimensionChange],
  )

  const handlePlayerClick = useCallback(
    (player: PlayerLocationEntry) => {
      if (player.region_dir_relpath === regionRelpath) {
        panToPlayerBlock(player.pos.x, player.pos.z)
        return
      }
      if (player.region_dir_relpath) {
        pendingPanRef.current = {
          dimRelpath: player.region_dir_relpath,
          bx: player.pos.x,
          bz: player.pos.z,
        }
        handleDimensionChange(player.region_dir_relpath)
      }
    },
    [regionRelpath, panToPlayerBlock, handleDimensionChange],
  )

  const popoverContext = useMemo(() => {
    if (!claimsPopover) return null
    for (const team of teams) {
      for (const cluster of team.clusters) {
        if (cluster.id !== claimsPopover.clusterId) continue
        const teamClustersInDim = team.clusters.filter(
          (c) => c.region_dir_relpath === cluster.region_dir_relpath,
        )
        const teamChunksInDim = teamClustersInDim.reduce(
          (s, c) => s + c.chunks.length,
          0,
        )
        return {
          team,
          cluster,
          teamChunksInDim,
          clustersInDim: teamClustersInDim.length,
        }
      }
    }
    return null
  }, [claimsPopover, teams])

  const dimensionOptions = useMemo(
    () =>
      buildDimensionOptions(
        layoutQ.data,
        labelsQ.data?.dimension_labels,
      ),
    [labelsQ.data?.dimension_labels, layoutQ.data],
  )

  const dimensionLabelByRelpath = useMemo(
    () => new Map(dimensionOptions.map((o) => [o.value, o.label])),
    [dimensionOptions],
  )
  const dimensionSelectValue = dimensionRelpath ?? null

  return {
    layoutQ,
    statusQ,
    serverInfoQ,
    serverStopped,
    mapStatusQ,
    mapInitialized,
    initOpen,
    initForce,
    setInitOpen,
    setInitForce,
    openInitDialog,
    handleInitComplete,
    handleInitClose,
    handleRefreshMap,
    dimensionRelpath,
    initialView,
    regionRelpath,
    rootList,
    dimensionOptions,
    dimensionLabelByRelpath,
    dimensionSelectValue,
    handleDimensionChange,
    handleViewChange,
    regionsMap,
    regionsLoading,
    regionsError,
    claimsQ,
    claimsAvailable,
    claimsOverlayVisible,
    setClaimsOverlayVisible,
    teams,
    claimsPopover,
    closeClaimsPopover,
    highlightClusters,
    handleRefreshClaims,
    handleClusterClick,
    popoverContext,
    playerLocationsQ,
    playersOverlayVisible,
    setPlayersOverlayVisible,
    onlinePlayersOnly,
    setOnlinePlayersOnly,
    onlinePlayersQ,
    onlinePlayerUuids,
    onlineStatusAvailable,
    playerProfiles,
    handleRefreshPlayers,
    handlePlayerClick,
    claimsOverlays,
    playersOverlays,
    mapOverlays,
    rawMode
  }
}
