import { http, HttpResponse } from 'msw'
import type { BackgroundTaskResponse, TaskEventResponse } from '@/features/tasks/contracts'
import type { OperationChanges } from '@/shared/operations/contracts'

export const taskEventsUnavailable = http.get('*/api/tasks/events', () => new HttpResponse(null, { status: 503 }))

export function taskResponse(taskId: string, overrides: Partial<BackgroundTaskResponse> = {}): BackgroundTaskResponse {
  return {
    task_id: taskId, task_type: 'snapshot_create', name: taskId, status: 'running',
    progress: null, progress_details: null, message: '正在处理', server_id: 'alpha',
    created_at: '2026-10-18T00:00:00Z', cancellable: true, ...overrides,
  }
}

export function taskEvent(task: BackgroundTaskResponse & { result_included?: boolean }): TaskEventResponse {
  const result = task.result ?? null
  const terminal = ['completed', 'failed', 'cancelled'].includes(task.status)
  const included = terminal && task.result_included !== false && new TextEncoder().encode(JSON.stringify(result)).byteLength <= 16 * 1024
  return { ...task, progress_details: task.progress_details ?? null, result_included: included, result: included ? result : null }
}

export function createTaskEvents(initial: BackgroundTaskResponse[] = [], domains: { activeRestorations?: unknown[]; pruneStates?: unknown[] } = {}) {
  let tasks = initial
  let activeRestorations = domains.activeRestorations ?? []
  let pruneStates = domains.pruneStates ?? []
  let connections = 0
  const requests: string[] = []
  const controllers = new Set<ReadableStreamDefaultController<Uint8Array>>()
  const encode = (event: unknown) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`)
  const snapshot = () => ({ type: 'snapshot', tasks: tasks.map(taskEvent), active_restorations: activeRestorations, prune_states: pruneStates })
  const broadcast = (event: unknown) => { for (const controller of controllers) controller.enqueue(encode(event)) }
  return {
    requests,
    get connections() { return connections },
    get activeConnections() { return controllers.size },
    handler: http.get('*/api/tasks/events', ({ request }) => {
      connections++
      requests.push(request.url)
      let owner: ReadableStreamDefaultController<Uint8Array>
      const close = () => {
        if (controllers.delete(owner)) owner.close()
        request.signal.removeEventListener('abort', close)
      }
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          owner = controller
          controllers.add(controller)
          controller.enqueue(encode(snapshot()))
          request.signal.addEventListener('abort', close, { once: true })
        },
        cancel() { controllers.delete(owner); request.signal.removeEventListener('abort', close) },
      })
      return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream' } })
    }),
    upsert(task: BackgroundTaskResponse & { result_included?: boolean }) {
      tasks = [...tasks.filter(row => row.task_id !== task.task_id), task]
      broadcast({ type: 'upsert', task: taskEvent(task) })
    },
    remove(taskId: string) {
      tasks = tasks.filter(task => task.task_id !== taskId)
      for (const controller of controllers) controller.enqueue(encode({ type: 'remove', task_id: taskId }))
    },
    replace(next: BackgroundTaskResponse[]) { tasks = next },
    snapshot() { broadcast(snapshot()) },
    raw(event: unknown) { broadcast(event) },
    operations(changes: OperationChanges) { broadcast({ type: 'operation_changes', changes }) },
    restorations(rows: unknown[]) { activeRestorations = rows; broadcast({ type: 'restoration_index', active_restorations: rows }) },
    pruneStates(rows: unknown[]) { pruneStates = rows; broadcast({ type: 'prune_state', prune_states: rows }) },
    heartbeat() { for (const controller of controllers) controller.enqueue(new TextEncoder().encode(': keepalive\n\n')) },
    malformed() { for (const controller of controllers) controller.enqueue(new TextEncoder().encode('data: {broken}\n\n: keepalive\n\n')) },
    close() { for (const controller of controllers) { controllers.delete(controller); controller.close() } },
  }
}
