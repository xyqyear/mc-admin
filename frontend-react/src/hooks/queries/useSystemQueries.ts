import { systemApi } from "@/hooks/api/systemApi";
import type { SystemInfo, SystemDiskUsage } from "@/types/ServerRuntime";
import { queryKeys } from "@/utils/api";
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

export const useSystemQueries = () => {
  // 系统信息 (中等频率更新，不包含CPU百分比)
  const useSystemInfo = (options?: UseQueryOptions<SystemInfo>) => {
    return useQuery({
      queryKey: queryKeys.system.info(),
      queryFn: systemApi.getSystemInfo,
      refetchInterval: 10000, // 10秒刷新系统信息
      staleTime: 5000, // 5秒
      ...options,
    });
  };

  // 系统CPU百分比 (较慢更新，因为需要1-2秒计算时间)
  const useSystemCpuPercent = (
    options?: UseQueryOptions<{ cpuPercentage: number }>
  ) => {
    return useQuery({
      queryKey: [...queryKeys.system.info(), "cpu"],
      queryFn: systemApi.getSystemCpuPercent,
      refetchInterval: 3000, // 3秒刷新CPU百分比（比其他系统信息慢）
      staleTime: 3000, // 3秒
      ...options,
    });
  };

  // 系统磁盘使用情况 (独立接口，中等频率更新)
  const useSystemDiskUsage = (options?: UseQueryOptions<SystemDiskUsage>) => {
    return useQuery({
      queryKey: queryKeys.system.diskUsage(),
      queryFn: systemApi.getSystemDiskUsage,
      refetchInterval: 30000, // 30秒刷新磁盘使用情况
      staleTime: 15000, // 15秒
      ...options,
    });
  };


  return {
    useSystemInfo, // 系统信息 (更新后的版本，不包含磁盘使用信息)
    useSystemCpuPercent, // 系统CPU百分比 (分离后的接口)
    useSystemDiskUsage, // 系统磁盘使用情况 (新的独立接口)
  };
};