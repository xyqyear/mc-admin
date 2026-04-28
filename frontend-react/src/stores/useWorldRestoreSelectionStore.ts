import { create } from 'zustand'

import type { ChunkKey } from '@/types/MapTypes'

// Per-server selection state for the world-restore page. Not persisted —
// selection is transient and intentionally disappears on reload.
//
// `dimension` stores the dimension's `region_dir_relpath` (the same value the
// backend expects on selection payloads). The relpath is unique across world
// roots because the root directory name is its first path segment, so this
// alone is enough to disambiguate selections in multi-world setups.
//
// `mode` is either `'chunk'` or `'region'`. Switching modes wipes the
// selection rather than trying to convert between representations.

export type WorldRestoreSelectionMode = 'chunk' | 'region'

export interface ServerSelectionState {
  mode: WorldRestoreSelectionMode
  dimension: string | null
  selection: Set<ChunkKey>
}

const emptyState = (): ServerSelectionState => ({
  mode: 'region',
  dimension: null,
  selection: new Set(),
})

interface WorldRestoreSelectionStore {
  byServer: Record<string, ServerSelectionState>
  getOrInit: (serverId: string) => ServerSelectionState
  setSelection: (serverId: string, selection: Set<ChunkKey>) => void
  setDimension: (serverId: string, dimension: string | null) => void
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
    // across dimensions.
    setDimension: (serverId, dimension) =>
      set((state) => {
        const prev = state.byServer[serverId] ?? emptyState()
        if (prev.dimension === dimension) return state
        return {
          byServer: {
            ...state.byServer,
            [serverId]: {
              ...prev,
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
        return {
          byServer: {
            ...state.byServer,
            [serverId]: { ...prev, mode, selection: new Set() },
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
