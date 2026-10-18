import { http, HttpResponse } from 'msw'
import type { BackgroundTaskResponse } from '@/features/tasks/contracts'

export const taskEventsUnavailable = http.get('*/api/tasks/events', () => new HttpResponse(null, { status: 503 }))

export function taskResponse(taskId: string, overrides: Partial<BackgroundTaskResponse> = {}): BackgroundTaskResponse {
  return {
    task_id: taskId, task_type: 'snapshot_create', name: taskId, status: 'running',
    progress: null, message: '正在处理', server_id: 'alpha',
    created_at: '2026-10-18T00:00:00Z', cancellable: true, ...overrides,
  }
}

export function createTaskEvents(initial: BackgroundTaskResponse[] = []) {
  let tasks = initial
  let connections = 0
  const controllers = new Set<ReadableStreamDefaultController<Uint8Array>>()
  const encode = (event: unknown) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`)
  const summary = (task: BackgroundTaskResponse) => {
    const result = { ...task }
    delete result.result
    return result
  }
  return {
    get connections() { return connections },
    get activeConnections() { return controllers.size },
    handler: http.get('*/api/tasks/events', ({ request }) => {
      connections++
      let owner: ReadableStreamDefaultController<Uint8Array>
      const close = () => {
        if (controllers.delete(owner)) owner.close()
        request.signal.removeEventListener('abort', close)
      }
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          owner = controller
          controllers.add(controller)
          controller.enqueue(encode({ type: 'snapshot', tasks: tasks.map(summary) }))
          request.signal.addEventListener('abort', close, { once: true })
        },
        cancel() { controllers.delete(owner); request.signal.removeEventListener('abort', close) },
      })
      return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream' } })
    }),
    upsert(task: BackgroundTaskResponse) {
      tasks = [...tasks.filter(row => row.task_id !== task.task_id), task]
      for (const controller of controllers) controller.enqueue(encode({ type: 'upsert', task: summary(task) }))
    },
    remove(taskId: string) {
      tasks = tasks.filter(task => task.task_id !== taskId)
      for (const controller of controllers) controller.enqueue(encode({ type: 'remove', task_id: taskId }))
    },
    replace(next: BackgroundTaskResponse[]) { tasks = next },
    heartbeat() { for (const controller of controllers) controller.enqueue(new TextEncoder().encode(': keepalive\n\n')) },
    malformed() { for (const controller of controllers) controller.enqueue(new TextEncoder().encode('data: {broken}\n\n: keepalive\n\n')) },
    close() { for (const controller of controllers) { controllers.delete(controller); controller.close() } },
  }
}
