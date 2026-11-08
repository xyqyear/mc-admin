import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'
import type { SettingsResource } from '@/features/settings/api'

export const settingsOptions = <T,>(resource: SettingsResource<T>) => ({
  queryKey: queryKeys.settings.detail(resource.key),
  queryFn: resource.read,
  staleTime: 5 * 60 * 1000,
})

export const useSettings = <T,>(resource: SettingsResource<T>) => useQuery(settingsOptions(resource))
