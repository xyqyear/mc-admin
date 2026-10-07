import { QueryObserver, queryOptions, type QueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'
import { snapshotApi } from './api'
import type { ActiveRestorations } from './contracts'

type ActiveRestorationKey = ReturnType<typeof queryKeys.snapshots.active>
type PollingObserver = QueryObserver<ActiveRestorations, Error, ActiveRestorations, ActiveRestorations, ActiveRestorationKey>
type SharedPolling = { observer: PollingObserver; consumers: number; unsubscribe: () => void }

// Query observers share requests, but each polling observer owns a separate timer.
const pollingByClient = new WeakMap<QueryClient, Map<string | undefined, SharedPolling>>()

export function activeRestorationsQueryOptions(serverId?: string) {
  return queryOptions({
    queryKey: queryKeys.snapshots.active(serverId),
    queryFn: ({ signal }) => snapshotApi.active(serverId, signal),
    staleTime: 0,
  })
}

export function retainActiveRestorationPolling(client: QueryClient, serverId?: string) {
  let polling = pollingByClient.get(client)
  if (!polling) {
    polling = new Map()
    pollingByClient.set(client, polling)
  }
  let shared = polling.get(serverId)
  if (!shared) {
    const observer = new QueryObserver(client, {
      ...activeRestorationsQueryOptions(serverId),
      refetchOnMount: false,
      refetchOnWindowFocus: 'always',
      refetchOnReconnect: 'always',
      refetchInterval: query => query.state.status !== 'success' || !query.state.data || query.state.data.restorations.length ? 2000 : 30000,
    })
    shared = { observer, consumers: 0, unsubscribe: observer.subscribe(() => {}) }
    polling.set(serverId, shared)
  }
  shared.consumers++
  const retained = shared
  return {
    refresh: () => retained.observer.refetch({ cancelRefetch: false }),
    release: () => {
      retained.consumers--
      if (retained.consumers) return
      retained.unsubscribe()
      polling.delete(serverId)
      if (!polling.size) pollingByClient.delete(client)
      void client.cancelQueries({ queryKey: queryKeys.snapshots.active(serverId), exact: true })
    },
  }
}
