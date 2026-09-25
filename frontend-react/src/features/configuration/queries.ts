import { queryOptions, useQuery } from '@tanstack/react-query'
import { queryKeys, shouldRetryQuery } from '@/shared/http/api'
import { configurationApi } from '@/features/configuration/api'
import type { ComposeConfiguration } from '@/features/configuration/contracts'

export const composeOptions = (serverId: string) => queryOptions({
  queryKey: queryKeys.compose.detail(serverId),
  queryFn: ({ signal }) => configurationApi.getCompose(serverId, signal),
  enabled: !!serverId,
  staleTime: 2 * 60 * 1000,
  retry: (count, error) => shouldRetryQuery(count, error, 2),
})

export const useComposeFile = (serverId: string, options?: { enabled?: boolean }) => useQuery<ComposeConfiguration, Error, string, ReturnType<typeof queryKeys.compose.detail>>({
  ...composeOptions(serverId), ...options, select: data => data.yaml_content,
})

export const useServerTemplatePreview = (serverId: string | null) => useQuery({
  queryKey: queryKeys.templates.serverConfigPreview(serverId ?? ''),
  queryFn: () => configurationApi.getServerTemplatePreview(serverId!),
  enabled: !!serverId,
  staleTime: 2 * 60 * 1000,
})

export const templateConfigOptions = (serverId: string) => queryOptions({
  queryKey: queryKeys.templates.serverConfig(serverId),
  queryFn: () => configurationApi.getServerTemplateConfig(serverId),
  enabled: !!serverId,
  staleTime: 2 * 60 * 1000,
})

export const useServerTemplateConfig = (serverId: string | null) => useQuery({
  ...templateConfigOptions(serverId ?? ''), enabled: !!serverId,
})
