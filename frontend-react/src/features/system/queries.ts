import { queryOptions } from '@tanstack/react-query';
import { systemApi } from "@/features/system/api";
import { queryKeys } from "@/shared/http/api";
import { useQuery } from "@tanstack/react-query";
export const useSystemQueries = () => {
  const useSystemInfo = (options?: Partial<Omit<ReturnType<typeof systemInfoQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...systemInfoQueryOptions(), ...options });
  };
  // Backend computes CPU% over a short sampling window (~1-2s), so polling
  // tighter than ~3s would show stale or noisy data.
  const useSystemCpuPercent = (options?: Partial<Omit<ReturnType<typeof systemCpuPercentQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...systemCpuPercentQueryOptions(), ...options });
  };
  const useSystemDiskUsage = (options?: Partial<Omit<ReturnType<typeof systemDiskUsageQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...systemDiskUsageQueryOptions(), ...options });
  };
  return {
    useSystemInfo,
    useSystemCpuPercent,
    useSystemDiskUsage,
  };
};
export const systemInfoQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.system.info(),
    queryFn: systemApi.getSystemInfo,
    refetchInterval: 10000,
    staleTime: 5000
  });
};
export const systemCpuPercentQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.system.cpuPercent(),
    queryFn: systemApi.getSystemCpuPercent,
    refetchInterval: 3000,
    staleTime: 3000
  });
};
export const systemDiskUsageQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.system.diskUsage(),
    queryFn: systemApi.getSystemDiskUsage,
    refetchInterval: 30000,
    staleTime: 15000
  });
};
