import api from '@/shared/http/api'
import type { DNSSettings, LogParserSettings, MapSettings, PlayerSettings, SelfCheckSettings, SnapshotSettings, WorldSettings } from '@/features/settings/contracts'

export interface SettingsResource<T> {
  key: string
  read: () => Promise<T>
  replace: (value: T) => Promise<T>
  reset: () => Promise<T>
}

function resource<T>(key: string): SettingsResource<T> {
  const path = `/settings/${key}`
  return {
    key,
    read: async () => (await api.get<T>(path)).data,
    replace: async value => (await api.put<T>(path, value)).data,
    reset: async () => (await api.post<T>(`${path}/reset`)).data,
  }
}

export const dnsSettings = resource<DNSSettings>('dns')
export const snapshotSettings = resource<SnapshotSettings>('snapshots')
export const logParserSettings = resource<LogParserSettings>('log-parser')
export const playerSettings = resource<PlayerSettings>('players')
export const mapSettings = resource<MapSettings>('mcmap')
export const worldSettings = resource<WorldSettings>('world')
export const selfCheckSettings = resource<SelfCheckSettings>('self-check')
