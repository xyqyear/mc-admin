import http from 'node:http'
import { once } from 'node:events'
import { StringDecoder } from 'node:string_decoder'

async function taskObservationFaultProxy(baseURL: string, interruptAfterSafetySnapshot: boolean, onEvent?: (event: Record<string, unknown>) => void) {
  let taskId = ''
  let disconnected = false
  let resumed = false
  let resolveCut!: () => void
  const interrupted = new Promise<void>(resolve => { resolveCut = resolve })
  const streams = new Map<http.ServerResponse, http.ClientRequest>()
  const interrupt = () => {
    disconnected = true
    for (const [response, upstream] of streams) {
      response.destroy()
      upstream.destroy()
    }
    resolveCut()
  }
  const server = http.createServer((request, response) => {
    const stream = request.method === 'GET' && new URL(request.url ?? '/', baseURL).pathname === '/api/tasks/events'
    const observation = request.method === 'GET' && taskId && request.url === `/api/tasks/${taskId}`
    if (!resumed && disconnected && (stream || observation)) {
      response.destroy()
      return
    }
    const upstream = http.request(new URL(request.url ?? '/', baseURL), { method: request.method, headers: { ...request.headers, host: new URL(baseURL).host } }, incoming => {
      const acceptance = interruptAfterSafetySnapshot && request.method === 'POST' && request.url === '/api/snapshots/restorations'
      if (stream && incoming.statusCode === 200) {
        streams.set(response, upstream)
        response.writeHead(200, incoming.headers)
        response.flushHeaders()
        const decoder = new StringDecoder('utf8')
        let buffer = ''
        incoming.on('data', (chunk: Buffer) => {
          buffer += decoder.write(chunk)
          let boundary: number
          while ((boundary = buffer.indexOf('\n\n')) !== -1) {
            const block = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n')
            if (!data) continue
            const event = JSON.parse(data) as { type: string; task?: { task_id: string; status: string; message: string }; tasks?: Array<{ task_id: string; status: string; message: string }> }
            onEvent?.(event)
            const task = event.type === 'upsert' ? event.task : event.tasks?.find(item => item.task_id === taskId)
            if (interruptAfterSafetySnapshot && !resumed && task?.task_id === taskId && task.status === 'running' && task.message === '正在恢复所选文件') {
              interrupt()
              return
            }
          }
          if (!response.destroyed) response.write(chunk)
        })
        incoming.on('end', () => response.end())
      } else if (acceptance || observation) {
        const chunks: Buffer[] = []
        incoming.on('data', (chunk: Buffer) => { chunks.push(chunk) })
        incoming.on('end', () => {
          const body = Buffer.concat(chunks)
          if (incoming.statusCode === 202 && acceptance) taskId = JSON.parse(body.toString()).task_id
          if (interruptAfterSafetySnapshot && observation && !resumed) {
            const task = incoming.statusCode === 200 ? JSON.parse(body.toString()) : null
            const ready = task?.status === 'running' && task.result?.safety_snapshot_id
            if (ready || disconnected) {
              interrupt()
              response.destroy()
              return
            }
          }
          response.writeHead(incoming.statusCode ?? 502, incoming.headers)
          response.end(body)
        })
      } else {
        response.writeHead(incoming.statusCode ?? 502, incoming.headers)
        incoming.pipe(response)
      }
      incoming.on('error', () => response.destroy())
    })
    upstream.on('error', () => response.destroy())
    response.on('close', () => {
      streams.delete(response)
      if (!response.writableFinished) upstream.destroy()
    })
    request.pipe(upstream)
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Failed to bind the owned task observation fault proxy.')
  return {
    url: `http://127.0.0.1:${address.port}`,
    interrupted,
    disconnect: (id: string) => { taskId = id; interrupt() },
    resume: () => { resumed = true },
    close: () => new Promise<void>((resolve, reject) => {
      server.close(error => { if (error) reject(error); else resolve() })
      server.closeAllConnections()
    }),
  }
}

export const interruptRestoreAfterSafetySnapshot = (baseURL: string) => taskObservationFaultProxy(baseURL, true)
export const createTaskObservationFault = (baseURL: string, onEvent?: (event: Record<string, unknown>) => void) => taskObservationFaultProxy(baseURL, false, onEvent)
