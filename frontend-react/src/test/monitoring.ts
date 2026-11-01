import type { MonitoringSnapshot, Sample } from '@/features/monitoring/contracts'
import type { ServerStatus } from '@/features/servers/contracts'

export function readySample<T>(value: T): Sample<T> {
  return { value, quality: 'ready', sampled_at: '2026-11-01T00:00:00Z', error: null }
}

export function monitoringFixture(status: ServerStatus = 'HEALTHY', cpu = 10): MonitoringSnapshot {
  return {
    system: {
      cpu_percent: readySample(20),
      memory: readySample({ used: 1024 ** 3, total: 8 * 1024 ** 3 }),
      load: readySample([1, 2, 3]),
      disk: readySample({ used: 1024 ** 3, total: 8 * 1024 ** 3, available: 7 * 1024 ** 3 }),
    },
    servers: {
      alpha: {
        generation: 1, incarnation: 'first-start', status: readySample(status),
        cpu_percent: status === 'CREATED' ? { value: null, quality: 'unavailable', sampled_at: null, error: '服务器未运行' } : readySample(cpu),
        memory_bytes: readySample(128), disk_io: readySample({ read: 100, write: 200 }),
        network_io: readySample({ read: 300, write: 400 }),
        disk: readySample({ used: 128, total: 1024, available: 896 }),
        maintenance: { active: false, kind: null, description: null, task_id: null },
      },
    },
  }
}
