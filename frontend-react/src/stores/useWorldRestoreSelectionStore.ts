import { create } from 'zustand'

import type { ChunkKey } from '@/types/MapTypes'
import {
  chunksToFullyCoveredRegions,
  regionToChunkKeys,
} from '@/components/map/coords'

// Per-server selection state for the world-restore page. Not persisted —
// selection is transient and intentionally disappears on reload.
//
// `dimension` stores the dimension's `region_dir_relpath` (the same value the
// backend expects on selection payloads), so switching dimensions clears the
// selection (different chunks live in different dimensions).
//
// `mode` is either `'chunk'` or `'region'`. The page-level switch promotes or
// demotes the selection set when the mode changes — see `setMode` below.

export type WorldRestoreSelectionMode = 'chunk' | 'region'

export interface ServerSelectionState {
  mode: WorldRestoreSelectionMode
  dimension: string | null
  worldRootName: string | null
  selection: Set<ChunkKey>
}

const emptyState = (): ServerSelectionState => ({
  mode: 'region',
  dimension: null,
  worldRootName: null,
  selection: new Set(),
})

interface WorldRestoreSelectionStore {
  byServer: Record<string, ServerSelectionState>
  getOrInit: (serverId: string) => ServerSelectionState
  setSelection: (serverId: string, selection: Set<ChunkKey>) => void
  setDimension: (
    serverId: string,
    worldRootName: string | null,
    dimension: string | null,
  ) => void
  setMode: (serverId: string, mode: WorldRestoreSelectionMode) => void
  clearForServer: (serverId: string) => void
}

const upsert = (
  state: WorldRestoreSelectionStore,
  serverId: string,
  patch: Partial<ServerSelectionState>,
): Record<string, ServerSelectionState> => {
  const prev = state.byServer[serverId] ?? emptyState()
  return {
    ...state.byServer,
    [serverId]: { ...prev, ...patch },
  }
}

export const useWorldRestoreSelectionStore = create<WorldRestoreSelectionStore>(
  (set, get) => ({
    byServer: {},

    getOrInit: (serverId) => get().byServer[serverId] ?? emptyState(),

    setSelection: (serverId, selection) =>
      set((state) => ({
        byServer: upsert(state, serverId, { selection }),
      })),

    // Switching dimension wipes the selection — chunks aren't comparable
    // across dimensions. Switching `worldRootName` similarly clears.
    setDimension: (serverId, worldRootName, dimension) =>
      set((state) => {
        const prev = state.byServer[serverId] ?? emptyState()
        const sameWorld = prev.worldRootName === worldRootName
        const sameDim = prev.dimension === dimension
        if (sameWorld && sameDim) return state
        return {
          byServer: {
            ...state.byServer,
            [serverId]: {
              ...prev,
              worldRootName,
              dimension,
              selection: new Set(),
            },
          },
        }
      }),

    setMode: (serverId, mode) =>
      set((state) => {
        const prev = state.byServer[serverId] ?? emptyState()
        if (prev.mode === mode) return state
        // chunk → region: keep only regions where every chunk is selected.
        // region → chunk: fan out (the selection is already represented as a
        // ChunkKey set, so this is a no-op on the data; only the displayed
        // semantics changes).
        let nextSelection = prev.selection
        if (prev.mode === 'chunk' && mode === 'region') {
          const fullRegions = chunksToFullyCoveredRegions(prev.selection)
          nextSelection = new Set<ChunkKey>()
          for (const r of fullRegions) {
            for (const k of regionToChunkKeys(r)) {
              nextSelection.add(k)
            }
          }
        }
        return {
          byServer: {
            ...state.byServer,
            [serverId]: { ...prev, mode, selection: nextSelection },
          },
        }
      }),

    clearForServer: (serverId) =>
      set((state) => {
        if (!(serverId in state.byServer)) return state
        const next = { ...state.byServer }
        delete next[serverId]
        return { byServer: next }
      }),
  }),
)
