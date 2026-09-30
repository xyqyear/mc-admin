import http from 'node:http'
import { once } from 'node:events'

export async function interruptRestoreAfterSafetySnapshot(baseURL: string) {
  let taskId = ''
  let disconnected = false
  let resumed = false
  let resolveCut!: () => void
  const interrupted = new Promise<void>(resolve => { resolveCut = resolve })
  const server = http.createServer((request, response) => {
    const upstream = http.request(new URL(request.url ?? '/', baseURL), { method: request.method, headers: { ...request.headers, host: new URL(baseURL).host } }, incoming => {
      const acceptance = request.method === 'POST' && request.url === '/api/snapshots/restorations'
      const observation = request.method === 'GET' && taskId && request.url === `/api/tasks/${taskId}`
      if (acceptance || observation) {
        const chunks: Buffer[] = []
        incoming.on('data', (chunk: Buffer) => { chunks.push(chunk) })
        incoming.on('end', () => {
          const body = Buffer.concat(chunks)
          if (incoming.statusCode === 202 && acceptance) taskId = JSON.parse(body.toString()).task_id
          if (observation && !resumed) {
            const ready = incoming.statusCode === 200 && JSON.parse(body.toString()).result?.safety_snapshot_id
            if (ready || disconnected) {
              disconnected = true
              response.destroy()
              resolveCut()
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
    response.on('close', () => { if (!response.writableFinished) upstream.destroy() })
    request.pipe(upstream)
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Failed to bind the owned task observation fault proxy.')
  return {
    url: `http://127.0.0.1:${address.port}`,
    interrupted,
    resume: () => { resumed = true },
    close: () => new Promise<void>((resolve, reject) => {
      server.close(error => { if (error) reject(error); else resolve() })
      server.closeAllConnections()
    }),
  }
}
