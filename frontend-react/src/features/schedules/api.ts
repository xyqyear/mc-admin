import { api } from '@/shared/http/api';
import type { RegisteredCronJob, CronJob, CronJobExecution, CronJobNextRunTime, CreateCronJobRequest, UpdateCronJobRequest, CreateCronJobResponse, UpdateCronJobResponse } from '@/features/schedules/contracts';


export const cronApi = {
  getRegisteredCronJobs: async (): Promise<RegisteredCronJob[]> => {
    const response = await api.get('/cron/registered')
    return response.data
  },

  getAllCronJobs: async (params?: {
    identifier?: string
    status?: string[]
  }): Promise<CronJob[]> => {
    const searchParams = new URLSearchParams()

    if (params?.identifier) {
      searchParams.append('identifier', params.identifier)
    }

    if (params?.status && params.status.length > 0) {
      params.status.forEach(s => searchParams.append('status', s))
    }

    const queryString = searchParams.toString()
    const url = queryString ? `/cron/?${queryString}` : '/cron/'

    const response = await api.get(url)
    return response.data
  },

  createCronJob: async (request: CreateCronJobRequest): Promise<CreateCronJobResponse> => {
    const response = await api.post('/cron/', request)
    return response.data
  },

  updateCronJob: async (cronjobId: string, request: UpdateCronJobRequest): Promise<UpdateCronJobResponse> => {
    const response = await api.put(`/cron/${cronjobId}`, request)
    return response.data
  },

  getCronJob: async (cronjobId: string): Promise<CronJob> => {
    const response = await api.get(`/cron/${cronjobId}`)
    return response.data
  },

  pauseCronJob: async (cronjobId: string): Promise<{ message: string }> => {
    const response = await api.post(`/cron/${cronjobId}/pause`)
    return response.data
  },

  resumeCronJob: async (cronjobId: string): Promise<{ message: string }> => {
    const response = await api.post(`/cron/${cronjobId}/resume`)
    return response.data
  },

  cancelCronJob: async (cronjobId: string): Promise<{ message: string }> => {
    const response = await api.delete(`/cron/${cronjobId}`)
    return response.data
  },

  getCronJobExecutions: async (
    cronjobId: string,
    limit: number = 50
  ): Promise<CronJobExecution[]> => {
    const response = await api.get(`/cron/${cronjobId}/executions`, {
      params: { limit }
    })
    return response.data
  },

  getCronJobNextRunTime: async (cronjobId: string): Promise<CronJobNextRunTime> => {
    const response = await api.get(`/cron/${cronjobId}/next-run-time`)
    return response.data
  }
}