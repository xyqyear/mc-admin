import { useConfirm } from '@/shared/hooks/useConfirm'
import { useCallback, useEffect } from 'react'
import { clusterToChunkKeys, teamDimChunkKeys } from '@/features/world/layers/claims/claimSelection'
import type { FtbClusterEntry, FtbTeamEntry } from '@/features/world/layers/claims/contracts'
import type { ChunkKey, SelectionMode } from '@/features/world/map/contracts'
import { setWorldMapMode, useWorldMapController } from '@/features/world/useWorldMapController'
import { useWorldRestoreSelectionStore, type WorldRestoreSelectionMode } from '@/features/world/restore/selectionStore'
const EMPTY_SELECTION = new Set<ChunkKey>()
export function useWorldRestoreController(serverId: string) {
  const world = useWorldMapController(serverId)
  const { dimensionRelpath, regionRelpath } = world
  const urlMode: WorldRestoreSelectionMode = world.rawMode === 'chunk' ? 'chunk' : 'region'
  const { confirm: confirmModeChange, confirmDialog: modeChangeConfirmDialog } = useConfirm()
  const selectionState = useWorldRestoreSelectionStore((s) =>
    s.byServer[serverId],
  )
  const setSelection = useWorldRestoreSelectionStore((s) => s.setSelection)
  const addToSelection = useWorldRestoreSelectionStore((s) => s.addToSelection)
  const setStoreDimension = useWorldRestoreSelectionStore((s) => s.setDimension)
  const setStoreMode = useWorldRestoreSelectionStore((s) => s.setMode)

  // The store wipes the selection when dim changes.
  useEffect(() => {
    if (!serverId) return
    setStoreDimension(serverId, dimensionRelpath)
  }, [serverId, dimensionRelpath, setStoreDimension])

  useEffect(() => {
    if (!serverId) return
    setStoreMode(serverId, urlMode)
  }, [serverId, urlMode, setStoreMode])

  const handleSelectionChange = useCallback(
    (next: Set<ChunkKey>) => {
      if (!serverId) return
      setSelection(serverId, next)
    },
    [serverId, setSelection],
  )

  const applyModeChange = useCallback(
    (next: WorldRestoreSelectionMode) => {
      setWorldMapMode(next)
    },
    [],
  )

  const handleModeChange = useCallback(
    (next: WorldRestoreSelectionMode) => {
      if (next === urlMode) return
      if (urlMode === 'region' && next === 'chunk') {
        confirmModeChange({
          title: '区块选择仍处于实验性',
          description:
            '区块模式目前仍处于实验性阶段，可能导致恢复范围不符合预期，甚至造成整个区域或区块损坏。除非万不得已，请优先使用区域选择。',
          cancelText: '留在区域选择',
          confirmText: '我了解风险，切换到区块选择',
          variant: 'destructive',
          onConfirm: () => applyModeChange(next),
        })
        return
      }
      applyModeChange(next)
    },
    [applyModeChange, confirmModeChange, urlMode],
  )

  const handleClusterSelect = useCallback(
    (cluster: FtbClusterEntry) => {
      if (!serverId) return
      // Cluster's dim must match the current dim — selection lives per dim.
      if (cluster.region_dir_relpath !== regionRelpath) return
      const keys = clusterToChunkKeys(cluster, urlMode)
      addToSelection(serverId, keys)
    },
    [serverId, regionRelpath, urlMode, addToSelection],
  )

  const handleTeamSelectInDim = useCallback(
    (team: FtbTeamEntry) => {
      if (!serverId || !regionRelpath) return
      const keys = teamDimChunkKeys(team, regionRelpath, urlMode)
      addToSelection(serverId, keys)
    },
    [serverId, regionRelpath, urlMode, addToSelection],
  )

  const selectionMode: SelectionMode = urlMode
  const selection = selectionState?.selection ?? EMPTY_SELECTION
  return { ...world, urlMode, modeChangeConfirmDialog, handleSelectionChange, handleModeChange, handleClusterSelect, handleTeamSelectInDim, selectionMode, selection }
}
