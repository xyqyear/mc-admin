import { performance } from 'node:perf_hooks'
import type { Page, Request } from '@playwright/test'
import type { OwnedEnvironment } from './fixtures'

interface RequestObservation { phase: string; method: string; endpoint: string; status: number | null; milliseconds: number; bytes: number; failed: boolean }

export class NetworkObservation {
  private phase = 'setup'
  private records: RequestObservation[] = []
  private started = new Map<Request, { phase: string; started: number }>()
  private pending = new Set<Promise<void>>()
  private windows: Array<{ name: string; milliseconds: number }> = []
  private context: Record<string, unknown> = {}
  constructor(private page: Page, private owned: OwnedEnvironment) {
    page.on('request', this.onRequest)
    page.on('requestfinished', this.onFinished)
    page.on('requestfailed', this.onFailed)
  }
  private onRequest = (request: Request) => {
    const url = new URL(request.url())
    if (url.origin === new URL(this.owned.base_url).origin && url.pathname.startsWith('/api/')) this.started.set(request, { phase: this.phase, started: performance.now() })
  }
  private endpoint(request: Request) {
    return new URL(request.url()).pathname.replaceAll(this.owned.server_id, ':server').replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi, ':id').replace(/\b[0-9a-f]{64}\b/gi, ':snapshot')
  }
  private record = async (request: Request, failed: boolean) => {
    const started = this.started.get(request)
    if (!started) return
    this.started.delete(request)
    const response = await request.response()
    const sizes = failed ? null : await request.sizes().catch(() => null)
    this.records.push({ phase: started.phase, method: request.method(), endpoint: this.endpoint(request), status: response?.status() ?? null, milliseconds: Math.round(performance.now() - started.started), bytes: sizes?.responseBodySize ?? 0, failed })
  }
  private track(request: Request, failed: boolean) {
    const done = this.record(request, failed).finally(() => this.pending.delete(done))
    this.pending.add(done)
  }
  private onFinished = (request: Request) => this.track(request, false)
  private onFailed = (request: Request) => this.track(request, true)

  async measure(name: string, action: () => Promise<void>) {
    this.phase = name
    const started = performance.now()
    try { await action() }
    finally { this.windows.push({ name, milliseconds: Math.round(performance.now() - started) }); this.phase = 'between-windows' }
  }
  describe(context: Record<string, unknown>) { this.context = { ...this.context, ...context } }
  async finish() {
    this.page.off('request', this.onRequest)
    this.page.off('requestfinished', this.onFinished)
    this.page.off('requestfailed', this.onFailed)
    await Promise.all(this.pending)
    return { schema: 1, run_id: this.owned.run_id, image_id: this.owned.image_id, browser: this.page.context().browser()?.version(), viewport: this.page.viewportSize(), context: this.context, windows: this.windows, requests: this.records, incomplete_requests: this.started.size, limits: 'One serial owned Chromium session; API network observations, not controlled performance estimates. No request/response bodies, credentials or query strings are recorded.' }
  }
}
