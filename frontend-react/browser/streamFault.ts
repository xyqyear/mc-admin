import http from 'node:http'
import { once } from 'node:events'

export async function interruptRestoreAfterSafetySnapshot(baseURL: string) {
  let cut = false
  let resolveCut!: () => void
  const interrupted = new Promise<void>(resolve => { resolveCut = resolve })
  const server = http.createServer((request, response) => {
    const upstream = http.request(new URL(request.url ?? '/', baseURL), { method: request.method, headers: { ...request.headers, host: new URL(baseURL).host } }, incoming => {
      response.writeHead(incoming.statusCode ?? 502, incoming.headers)
      let tail = ''
      incoming.on('data', (chunk: Buffer) => {
        response.write(chunk)
        if (!cut && request.method === 'POST' && request.url?.endsWith('/world-restore/restore')) {
          tail = (tail + chunk.toString('utf8')).slice(-16_384)
          if (/"event_type"\s*:\s*"safety_snapshot"/.test(tail) && /"safety_snapshot_id"\s*:\s*"[a-f0-9]+"/.test(tail)) {
            cut = true
            upstream.destroy()
            response.destroy()
            resolveCut()
          }
        }
      })
      incoming.on('end', () => response.end())
      incoming.on('error', () => response.destroy())
    })
    upstream.on('error', () => response.destroy())
    response.on('close', () => { if (!response.writableFinished) upstream.destroy() })
    request.pipe(upstream)
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Failed to bind the owned stream fault proxy.')
  return {
    url: `http://127.0.0.1:${address.port}`,
    interrupted,
    close: () => new Promise<void>((resolve, reject) => {
      server.close(error => { if (error) reject(error); else resolve() })
      server.closeAllConnections()
    }),
  }
}
