import type { ServerStatus } from '@/features/servers/contracts'

export interface Sample<T> {
  value: T | null
  sampled_at: string | null
  quality: 'ready' | 'pending' | 'stale' | 'unavailable'
  error: string | null
}

export interface MemoryUsage { used: number; total: number }
export interface DiskUsage extends MemoryUsage { available: number }
export interface ByteCounters { read: number; write: number }
export interface ServerMaintenance {
  active: boolean
  kind: string | null
  description: string | null
  task_id: string | null
}

export interface ServerSamples {
  generation: number
  incarnation: string | null
  status: Sample<ServerStatus>
  cpu_percent: Sample<number>
  memory_bytes: Sample<number>
  disk_io: Sample<ByteCounters>
  network_io: Sample<ByteCounters>
  disk: Sample<DiskUsage>
  maintenance: ServerMaintenance
}

export interface MonitoringSnapshot {
  system: {
    cpu_percent: Sample<number>
    memory: Sample<MemoryUsage>
    load: Sample<[number, number, number]>
    disk: Sample<DiskUsage>
  }
  servers: Record<string, ServerSamples>
}
