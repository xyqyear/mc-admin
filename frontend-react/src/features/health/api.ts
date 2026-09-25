import { api } from '@/shared/http/api';
import type { SelfCheckRunResult, SelfCheckCatalogItem, SelfCheckRunDetail, SelfCheckRunsResponse, SelfCheckStatusResponse } from '@/features/health/contracts';


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