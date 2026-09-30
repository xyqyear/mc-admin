import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'

export interface MapRevision { time: number; id: string }

export function latestMapRevision(a: MapRevision | null | undefined, b: MapRevision | null | undefined) {
  if (!a) return b ?? null
  if (!b) return a
  return a.time > b.time || (a.time === b.time && a.id > b.id) ? a : b
}

export function useMapRevision(serverId: string) {
  const global = useQuery<MapRevision | null>({ queryKey: queryKeys.map.revision(), queryFn: () => null, enabled: false, gcTime: Infinity })
  const server = useQuery<MapRevision | null>({ queryKey: queryKeys.map.revision(serverId), queryFn: () => null, enabled: false, gcTime: Infinity })
  const revision = latestMapRevision(global.data, server.data)
  return revision ? `${revision.time}-${revision.id}` : undefined
}
