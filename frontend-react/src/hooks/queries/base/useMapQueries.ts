import { useQuery } from '@tanstack/react-query'

import { mapApi } from '@/hooks/api/mapApi'
import { queryKeys } from '@/utils/api'

export const useMapStatus = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.map.status(serverId || ''),
    queryFn: () => mapApi.getStatus(serverId!),
    enabled: !!serverId,
    staleTime: 1000 * 30,
  })

export const useMapDimensions = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.map.dimensions(serverId || ''),
    queryFn: () => mapApi.getDimensions(serverId!),
    enabled: !!serverId,
    staleTime: 1000 * 60,
  })

export const useMapRegions = (
  serverId: string | undefined,
  regionPath: string | undefined,
) =>
  useQuery({
    queryKey: queryKeys.map.regions(serverId || '', regionPath || ''),
    queryFn: () => mapApi.getRegions(serverId!, regionPath!),
    enabled: !!serverId && !!regionPath,
    staleTime: 1000 * 60,
  })
