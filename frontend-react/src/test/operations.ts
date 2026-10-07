import { http, HttpResponse } from 'msw'
import type { Operation, OperationChange, OperationChanges } from '@/shared/operations/contracts'

export function createOperationFeed(activeCount = 0) {
  let sequence = 0
  let instance = 1
  const items: OperationChange[] = []
  const requests: (string | null)[] = []
  return {
    requests,
    publish(...operations: Operation[]) {
      for (const operation of operations) items.push({ ...operation, resources: [...operation.resources], sequence: ++sequence })
    },
    restart() { instance++; sequence = 0; items.length = 0 },
    setActiveCount(count: number) { activeCount = count },
    handler: http.get('*/api/operations/changes', ({ request }) => {
      const url = new URL(request.url)
      const cursor = url.searchParams.get('cursor')
      requests.push(cursor)
      const [epoch, position] = cursor?.split(':') ?? []
      const reset = !cursor || Number(epoch) !== instance
      const page = reset ? [] : items.filter(item => item.sequence > Number(position)).slice(0, Number(url.searchParams.get('limit')) || 200)
      const last = page.at(-1)?.sequence ?? sequence
      const response: OperationChanges = { items: page, next_cursor: `${instance}:${last}`, has_more: last < sequence, active_count: activeCount, reset_required: reset }
      return HttpResponse.json(response)
    }),
  }
}
