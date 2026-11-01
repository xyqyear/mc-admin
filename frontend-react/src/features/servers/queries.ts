import { queryOptions } from '@tanstack/react-query';
import { shouldRetryQuery } from '@/shared/http/api';
import { serverApi } from "@/features/servers/api";

import { queryKeys } from "@/shared/http/api";
import { useQuery } from "@tanstack/react-query";
export const useServers = (options?: Partial<Omit<ReturnType<typeof serversQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serversQueryOptions(), ...options });
};

export const useServerInfo = (id: string, options?: Partial<Omit<ReturnType<typeof serverInfoQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverInfoQueryOptions(id), ...options });
};

export const useRestartSchedule = (id: string, options?: Partial<Omit<ReturnType<typeof restartScheduleQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...restartScheduleQueryOptions(id), ...options });
};

export const serversQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.servers(),
    queryFn: serverApi.getServers,
    staleTime: 5 * 60 * 1000,
    refetchInterval: false,
    gcTime: 10 * 60 * 1000
  });
};
export const serverInfoQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.serverInfos.detail(id),
    queryFn: () => serverApi.getServerInfo(id),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000
  });
};
export const restartScheduleQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.restartSchedule.detail(id),
    queryFn: () => serverApi.getRestartSchedule(id),
    enabled: !!id,
    staleTime: 2 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
