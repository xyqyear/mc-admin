export type RegistrationStatus = 'registered' | 'pending' | 'failed' | 'blocked' | 'inactive'

import type { RJSFSchema } from '@rjsf/utils';

export interface RegisteredCronJob {
  identifier: string
  description: string
  parameter_schema: RJSFSchema
  is_system: boolean
  default_cron?: string | null
  default_second?: string | null
  default_params?: Record<string, any> | null
  default_name?: string | null
}

export interface CronJob {
  registration_status?: RegistrationStatus
  registration_error?: string | null
  managed_server_generation?: number | null
  managed_purpose?: 'restart' | null
  managed_binding_issue?: string | null
  cronjob_id: string
  identifier: string
  name: string
  cron: string
  second?: string
  params: Record<string, any>
  execution_count: number
  is_system: boolean
  status: string // lowercase 'active' | 'paused' | 'cancelled'
  created_at: string
  updated_at: string
}

export interface CronJobExecution {
  execution_id: string
  started_at?: string
  ended_at?: string
  duration_ms?: number
  status: 'running' | 'completed' | 'skipped' | 'failed' | 'cancelled'
  messages: string[]
}

export interface CronJobNextRunTime {
  cronjob_id: string
  next_run_time: string
}

export interface CreateCronJobRequest {
  identifier: string
  params: Record<string, any>
  cron: string
  cronjob_id?: string
  name?: string
  second?: string
}

export interface UpdateCronJobRequest {
  identifier: string
  params: Record<string, any>
  cron: string
  name?: string
  second?: string
}

export interface CreateCronJobResponse {
  cronjob_id: string
  message: string
}

export interface UpdateCronJobResponse {
  message: string
}
