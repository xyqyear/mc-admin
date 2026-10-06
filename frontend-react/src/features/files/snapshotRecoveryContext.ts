import { createContext, useContext } from 'react'

export const SnapshotRecoveryContext = createContext<{
  busy: boolean
  create: (paths: string[], label: string) => void
  restore: (paths: string[], label?: string) => void
  history: () => void
} | null>(null)

export function useFileSnapshotRecovery() {
  const recovery = useContext(SnapshotRecoveryContext)
  if (!recovery) throw new Error('File snapshot actions require a recovery owner')
  return recovery
}
