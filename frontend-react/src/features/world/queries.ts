import { useQuery } from '@tanstack/react-query'
import { worldApi } from '@/features/world/api'
import { queryKeys } from '@/shared/http/api'

export const useWorldLayout = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.worldRestore.layout(serverId ?? ''),
    queryFn: () => worldApi.getLayout(serverId!),
    enabled: !!serverId,
    staleTime: 30_000,
  })

export const useWorldDimensionLabels = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.worldRestore.dimensionLabels(serverId ?? ''),
    queryFn: () => worldApi.getDimensionLabels(serverId!),
    enabled: !!serverId,
  })

export const useWorldPlayerLocations = (
  serverId: string | undefined,
  enabled = true,
) =>
  useQuery({
    queryKey: queryKeys.worldRestore.playerLocations(serverId ?? ''),
    queryFn: () => worldApi.getPlayerLocations(serverId!),
    enabled: !!serverId && enabled,
    staleTime: 30_000,
  })

export const useMapStatus = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.map.status(serverId || ''),
    queryFn: () => worldApi.getStatus(serverId!),
    enabled: !!serverId,
    staleTime: 1000 * 30,
  })

export const useMapRegions = (
  serverId: string | undefined,
  regionPath: string | undefined,
) =>
  useQuery({
    queryKey: queryKeys.map.regions(serverId || '', regionPath || ''),
    queryFn: () => worldApi.getRegions(serverId!, regionPath!),
    enabled: !!serverId && !!regionPath,
    staleTime: 1000 * 60,
  })
export const useFtbClaims = (serverId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: queryKeys.ftbClaims.claims(serverId ?? ''),
    queryFn: () => worldApi.getClaims(serverId!),
    enabled: !!serverId && enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
