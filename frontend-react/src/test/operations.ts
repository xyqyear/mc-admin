import { http, HttpResponse } from 'msw'
import type { Operation, OperationChange, OperationChanges } from '@/shared/operations/contracts'
import type { BackgroundTaskResponse } from '@/features/tasks/contracts'
import { taskEvent } from './taskEvents'

export function createOperationFeed(activeCount = 0) {
  let sequence = 0
  let instance = 1
  const items: OperationChange[] = []
  const requests: (string | null)[] = []
  let tasks: BackgroundTaskResponse[] = []
  const subscribers = new Map<ReadableStreamDefaultController<Uint8Array>, string | null>()
  const encode = (event: unknown) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`)
  const cursor = () => `${instance}:${sequence}`
  const drain = (controller: ReadableStreamDefaultController<Uint8Array>) => {
    const from = subscribers.get(controller)
    const [epoch, position] = from?.split(':') ?? []
    const reset = !from || Number(epoch) !== instance || !Number.isInteger(Number(position)) || Number(position) > sequence
    const page = reset ? [] : items.filter(item => item.sequence > Number(position))
    do {
      const batch = page.splice(0, 200)
      const next = reset ? sequence : batch.at(-1)?.sequence ?? sequence
      const response: OperationChanges = { items: batch, next_cursor: `${instance}:${next}`, has_more: page.length > 0, active_count: activeCount, reset_required: reset }
      controller.enqueue(encode({ type: 'operation_changes', changes: response }))
      subscribers.set(controller, response.next_cursor)
    } while (page.length)
  }
  return {
    requests,
    get cursor() { return cursor() },
    get activeConnections() { return subscribers.size },
    upsertTask(task: BackgroundTaskResponse) {
      tasks = [...tasks.filter(item => item.task_id !== task.task_id), task]
      for (const controller of subscribers.keys()) controller.enqueue(encode({ type: 'upsert', task: taskEvent(task) }))
    },
    replaceTasks(next: BackgroundTaskResponse[]) {
      tasks = next
      for (const controller of subscribers.keys()) controller.enqueue(encode({ type: 'snapshot', tasks: tasks.map(taskEvent), active_restorations: [], prune_states: [] }))
    },
    publish(...operations: Operation[]) {
      for (const operation of operations) items.push({ ...operation, resources: [...operation.resources], sequence: ++sequence })
      for (const controller of subscribers.keys()) drain(controller)
    },
    restart() { instance++; sequence = 0; items.length = 0; for (const controller of subscribers.keys()) drain(controller) },
    setActiveCount(count: number) { activeCount = count },
    close() { for (const controller of subscribers.keys()) { subscribers.delete(controller); controller.close() } },
    handler: http.get('*/api/tasks/events', ({ request }) => {
      const from = new URL(request.url).searchParams.get('operation_cursor')
      requests.push(from)
      let owner: ReadableStreamDefaultController<Uint8Array>
      const close = () => { if (subscribers.delete(owner)) owner.close(); request.signal.removeEventListener('abort', close) }
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          owner = controller
          subscribers.set(controller, from)
          controller.enqueue(encode({ type: 'snapshot', tasks: tasks.map(taskEvent), active_restorations: [], prune_states: [] }))
          drain(controller)
          request.signal.addEventListener('abort', close, { once: true })
        },
        cancel() { subscribers.delete(owner); request.signal.removeEventListener('abort', close) },
      })
      return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream' } })
    }),
  }
}
