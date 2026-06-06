import { api } from '@/utils/api'

export type SelfCheckSeverity = 'success' | 'info' | 'warning' | 'critical'
export type SelfCheckFindingStatus =
  | 'passed'
  | 'info'
  | 'warning'
  | 'critical'
  | 'skipped'
  | 'failed'
export type SelfCheckRunStatus = 'success' | 'warning' | 'critical'
export type SelfCheckRunScope = 'full' | 'check'
export type SelfCheckRunEventType =
  | 'started'
  | 'check_started'
  | 'check_finished'
  | 'completed'
  | 'error'

export interface SelfCheckFinding {
  check_id: string
  category: string
  severity: SelfCheckSeverity
  status: SelfCheckFindingStatus
  title: string
  message: string
  server_id?: string | null
  evidence: Record<string, any>
  remediation: string[]
  created_at: string
}

export interface SelfCheckSummary {
  total: number
  passed: number
  skipped: number
  info: number
  warning: number
  critical: number
  failed: number
  status: SelfCheckRunStatus
}

export interface SelfCheckRunResult {
  id: string
  trigger: string
  scope: SelfCheckRunScope
  check_id?: string | null
  status: SelfCheckRunStatus
  started_at: string
  finished_at: string
  duration_ms: number
  summary: SelfCheckSummary
  findings: SelfCheckFinding[]
  error_message?: string | null
}

export interface SelfCheckCatalogItem {
  check_id: string
  category: string
  title: string
  description: string
  enabled: boolean
}

export interface SelfCheckRunSummaryRecord {
  id: string
  trigger: string
  scope: SelfCheckRunScope
  check_id?: string | null
  status: SelfCheckRunStatus
  started_at: string
  finished_at: string
  duration_ms: number
  summary: SelfCheckSummary
  requested_by_user_id?: number | null
  error_message?: string | null
}

export interface SelfCheckRunDetail extends SelfCheckRunSummaryRecord {
  findings: SelfCheckFinding[]
}

export interface SelfCheckCurrentState {
  status: SelfCheckRunStatus
  updated_at: string
  source_run_id: string
  summary: SelfCheckSummary
  findings: SelfCheckFinding[]
}

export interface SelfCheckRunsResponse {
  runs: SelfCheckRunSummaryRecord[]
  total: number
}

export interface SelfCheckStatusResponse extends SelfCheckRunsResponse {
  catalog: SelfCheckCatalogItem[]
  current_state?: SelfCheckCurrentState | null
  retention_runs_keep_days: number
}

export interface SelfCheckRunEvent {
  type: SelfCheckRunEventType
  run_id: string
  trigger: string
  scope: SelfCheckRunScope
  check_id?: string | null
  total_checks?: number | null
  started_at?: string | null
  finished_at?: string | null
  findings?: SelfCheckFinding[] | null
  result?: SelfCheckRunResult | null
  message?: string | null
}

export const selfCheckApi = {
  getCatalog: async (): Promise<SelfCheckCatalogItem[]> => {
    const response = await api.get('/self-check/catalog')
    return response.data
  },

  getStatus: async (): Promise<SelfCheckStatusResponse> => {
    const response = await api.get('/self-check/status')
    return response.data
  },

  getRuns: async (
    params?: { limit?: number; offset?: number }
  ): Promise<SelfCheckRunsResponse> => {
    const response = await api.get('/self-check/runs', { params })
    return response.data
  },

  getRun: async (runId: string): Promise<SelfCheckRunDetail> => {
    const response = await api.get(`/self-check/runs/${runId}`)
    return response.data
  },

  runSelfCheck: async (): Promise<SelfCheckRunResult> => {
    const response = await api.post('/self-check/run')
    return response.data
  },

  runSelfCheckItem: async (checkId: string): Promise<SelfCheckRunResult> => {
    const response = await api.post(`/self-check/checks/${encodeURIComponent(checkId)}/run`)
    return response.data
  },
}
