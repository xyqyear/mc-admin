export type RegistrationStatus = 'registered' | 'pending' | 'failed' | 'inactive'

export type JobIdentifier = 'restart_server' | 'backup' | 'self_check'

export interface BackupParameters {
  server_id?: string | null
  path?: string | null
  enable_forget: boolean
  keep_last?: number | null
  keep_hourly?: number | null
  keep_daily?: number | null
  keep_weekly?: number | null
  keep_monthly?: number | null
  keep_yearly?: number | null
  keep_tag?: string[] | null
  keep_within?: string | null
  prune: boolean
  uptimekuma_url?: string | null
}

export type JobParameters =
  | { identifier: 'restart_server'; params: { server_id: string } }
  | { identifier: 'backup'; params: BackupParameters }
  | { identifier: 'self_check'; params: { scope: string } }

export interface RegisteredCronJob {
  identifier: JobIdentifier
  description: string
  is_system: boolean
  default_cron?: string | null
  default_second?: string | null
  default_params?: Record<string, any> | null
  default_name?: string | null
}

export interface CronJob {
  registration_status?: RegistrationStatus
  registration_error?: string | null
  managed_purpose?: 'restart' | null
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

interface ScheduleInput {
  cron: string
  cronjob_id?: string
  name?: string
  second?: string
}

export type CreateCronJobRequest = ScheduleInput & JobParameters
export type UpdateCronJobRequest = ScheduleInput & JobParameters

export interface CreateCronJobResponse {
  cronjob_id: string
  message: string
}

export interface UpdateCronJobResponse {
  message: string
}
