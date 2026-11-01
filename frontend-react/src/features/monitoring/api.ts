import { api } from '@/shared/http/api'
import type { MonitoringSnapshot } from './contracts'

export async function getMonitoring(signal: AbortSignal): Promise<MonitoringSnapshot> {
  return (await api.get<MonitoringSnapshot>('/monitoring', { signal, timeout: 5000 })).data
}
