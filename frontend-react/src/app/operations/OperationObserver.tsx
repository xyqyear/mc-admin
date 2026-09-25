import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { api, AUTH_EXPIRED_EVENT, getErrorStatus, queryKeys } from '@/shared/http/api'
import { filesOperationResources } from '@/features/files/operationResources'
import { worldOperationResources } from '@/features/world/operationResources'
import { configurationOperationResources } from '@/features/configuration/operationResources'
import { isTerminalOperation, type Operation } from '@/shared/operations/contracts'

const resourceRegistrations: ((operation: Operation) => QueryKey[])[] = [configurationOperationResources, filesOperationResources, worldOperationResources]
type ObservedOperation = Operation & { unavailable?: true }
const isSettled = (operation: ObservedOperation) => operation.unavailable === true || isTerminalOperation(operation)

async function readOperations(signal: AbortSignal, previous: ObservedOperation[] = []): Promise<ObservedOperation[]> {
  const operations = new Map<string, ObservedOperation>()
  const known = new Set(previous.map(operation => operation.operation_id))
  const limit = 1000
  for (let offset = 0; ; offset += limit) {
    const { data } = await api.get<Operation[]>('/operations', { params: { limit, offset }, signal })
    for (const operation of data) operations.set(operation.operation_id, operation)
    if (data.length < limit || data.some(operation => known.has(operation.operation_id))) break
  }
  for (const operation of previous) {
    if (isSettled(operation) || operations.has(operation.operation_id)) continue
    try {
      const { data } = await api.get<Operation>(`/operations/${operation.operation_id}`, { signal })
      operations.set(data.operation_id, data)
    } catch (error) {
      if (getErrorStatus(error) !== 404) throw error
      operations.set(operation.operation_id, { ...operation, unavailable: true })
    }
  }
  return [...operations.values()]
}

export function OperationObserver({ sessionId }: { sessionId: string }) {
  const client = useQueryClient()
  const handled = useRef(new Set<string>())
  const { data } = useQuery({
    queryKey: queryKeys.operations.session(sessionId),
    queryFn: ({ signal }) => readOperations(signal, client.getQueryData<ObservedOperation[]>(queryKeys.operations.session(sessionId))),
    staleTime: 0,
    refetchOnReconnect: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: query => query.state.data?.some(operation => !isSettled(operation)) ? 2000 : 10000,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    const seen = handled.current
    const clear = () => seen.clear()
    window.addEventListener(AUTH_EXPIRED_EVENT, clear)
    const unsubscribe = client.getQueryCache().subscribe(event => {
      if (event.type === 'removed' && event.query.queryKey[0] === queryKeys.operations.all[0]) clear()
    })
    return () => { unsubscribe(); window.removeEventListener(AUTH_EXPIRED_EVENT, clear) }
  }, [client, sessionId])

  useEffect(() => {
    const keys = new Map<string, QueryKey>()
    for (const operation of data ?? []) {
      if (!isSettled(operation) || handled.current.has(operation.operation_id)) continue
      handled.current.add(operation.operation_id)
      for (const registration of resourceRegistrations) {
        for (const key of registration(operation)) keys.set(JSON.stringify(key), key)
      }
    }
    for (const key of keys.values()) void client.invalidateQueries({ queryKey: key })
  }, [client, data])

  return null
}
