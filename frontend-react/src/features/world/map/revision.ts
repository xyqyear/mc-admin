import { useQuery, type QueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'

export interface MapRevision { time: number; id: string; sequence?: number }

export function latestMapRevision(a: MapRevision | null | undefined, b: MapRevision | null | undefined) {
  if (!a) return b ?? null
  if (!b) return a
  if (a.sequence !== undefined && b.sequence !== undefined && a.sequence !== b.sequence) return a.sequence > b.sequence ? a : b
  return a.time > b.time || (a.time === b.time && a.id > b.id) ? a : b
}

export function useMapRevision(serverId: string) {
  const reset = useQuery<string | null>({ queryKey: queryKeys.map.resetRevision(), queryFn: () => null, enabled: false, gcTime: Infinity })
  const global = useQuery<MapRevision | null>({ queryKey: queryKeys.map.revision(), queryFn: () => null, enabled: false, gcTime: Infinity })
  const server = useQuery<MapRevision | null>({ queryKey: queryKeys.map.revision(serverId), queryFn: () => null, enabled: false, gcTime: Infinity })
  const revision = latestMapRevision(global.data, server.data)
  return [reset.data, revision ? `${revision.sequence ?? revision.time}-${revision.id}` : null].filter(Boolean).join(':') || undefined
}

export function resetMapRevision(client: QueryClient, cursor: string) {
  client.setQueryDefaults(queryKeys.map.revisions(), { gcTime: Infinity })
  for (const query of client.getQueryCache().findAll({ queryKey: queryKeys.map.revisions() })) {
    const revision = query.state.data as MapRevision | null | undefined
    if (revision && typeof revision === 'object') client.setQueryData(query.queryKey, { ...revision, sequence: 0 })
  }
  client.setQueryData(queryKeys.map.resetRevision(), `${cursor}:${Date.now()}:${Math.random().toString(36).slice(2)}`)
}
