import { systemApi } from "@/hooks/api/systemApi";
import type { SystemInfo, SystemDiskUsage } from "@/types/ServerRuntime";
import { queryKeys } from "@/utils/api";
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

export const useSystemQueries = () => {
  const useSystemInfo = (options?: UseQueryOptions<SystemInfo>) => {
    return useQuery({
      queryKey: queryKeys.system.info(),
      queryFn: systemApi.getSystemInfo,
      refetchInterval: 10000,
      staleTime: 5000,
      ...options,
    });
  };

  // Backend computes CPU% over a short sampling window (~1-2s), so polling
  // tighter than ~3s would show stale or noisy data.
  const useSystemCpuPercent = (
    options?: UseQueryOptions<{ cpuPercentage: number }>
  ) => {
    return useQuery({
      queryKey: queryKeys.system.cpuPercent(),
      queryFn: systemApi.getSystemCpuPercent,
      refetchInterval: 3000,
      staleTime: 3000,
      ...options,
    });
  };

  const useSystemDiskUsage = (options?: UseQueryOptions<SystemDiskUsage>) => {
    return useQuery({
      queryKey: queryKeys.system.diskUsage(),
      queryFn: systemApi.getSystemDiskUsage,
      refetchInterval: 30000,
      staleTime: 15000,
      ...options,
    });
  };


  return {
    useSystemInfo,
    useSystemCpuPercent,
    useSystemDiskUsage,
  };
};
