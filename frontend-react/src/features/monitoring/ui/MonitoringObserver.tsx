import { useEffect, useSyncExternalStore } from 'react'
import { focusManager, onlineManager, useQuery, useQueryClient } from '@tanstack/react-query'
import { monitoringQueryOptions } from '../queries'
import { queryKeys } from '@/shared/http/api'

const subscribeFocus = (notify: () => void) => focusManager.subscribe(notify)
const subscribeOnline = (notify: () => void) => onlineManager.subscribe(notify)
const focused = () => focusManager.isFocused()
const online = () => onlineManager.isOnline()

export function MonitoringObserver({ userId }: { userId: number }) {
  const client = useQueryClient()
  const visible = useSyncExternalStore(subscribeFocus, focused)
  const connected = useSyncExternalStore(subscribeOnline, online)
  useQuery({
    ...monitoringQueryOptions(userId),
    enabled: visible && connected,
    refetchInterval: visible && connected ? 2000 : false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  useEffect(() => () => { void client.cancelQueries({ queryKey: queryKeys.monitoring.snapshot(userId) }) }, [client, userId])
  return null
}
