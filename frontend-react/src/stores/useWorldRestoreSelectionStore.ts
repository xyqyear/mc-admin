import { create } from 'zustand'

import type { ChunkKey } from '@/types/MapTypes'

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
  // Union new keys into the existing selection.
  addToSelection: (serverId: string, keys: Set<ChunkKey>) => void
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

    addToSelection: (serverId, keys) =>
      set((state) => {
        if (keys.size === 0) return state
        const prev = state.byServer[serverId] ?? emptyState()
        const next = new Set(prev.selection)
        for (const k of keys) next.add(k)
        if (next.size === prev.selection.size) return state
        return {
          byServer: {
            ...state.byServer,
            [serverId]: { ...prev, selection: next },
          },
        }
      }),

    // Wipes the selection — chunk keys aren't comparable across dimensions.
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
