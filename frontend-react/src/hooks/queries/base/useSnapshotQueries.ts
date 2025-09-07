import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { 
  snapshotApi, 
  type Snapshot, 
  type BackupRepositoryUsage
} from "@/hooks/api/snapshotApi";
import { queryKeys } from "@/utils/api";

export const useSnapshotQueries = () => {
  // 获取所有快照列表
  const useGlobalSnapshots = (options?: UseQueryOptions<Snapshot[]>) => {
    return useQuery({
      queryKey: queryKeys.snapshots.global(),
      queryFn: () => snapshotApi.getAllSnapshots(),
      staleTime: 2 * 60 * 1000, // 2分钟 - 快照列表变化较慢
      refetchInterval: false, // 不自动刷新，手动操作时刷新
      ...options,
    });
  };

  // 获取特定路径的快照列表
  const useSnapshotsForPath = (
    serverId: string | null, 
    path: string | null,
    enabled: boolean = true,
    options?: UseQueryOptions<Snapshot[]>
  ) => {
    return useQuery({
      queryKey: queryKeys.snapshots.forPath(serverId || "", path || ""),
      queryFn: () => snapshotApi.getAllSnapshots({ 
        server_id: serverId!, 
        path: path! 
      }),
      enabled: enabled && !!serverId && !!path,
      staleTime: 1 * 60 * 1000, // 1分钟 - 路径相关快照需要较新的数据
      refetchInterval: false,
      ...options,
    });
  };

  // 备份仓库使用情况 (快照模块的独立接口)
  const useBackupRepositoryUsage = (options?: UseQueryOptions<BackupRepositoryUsage>) => {
    return useQuery({
      queryKey: queryKeys.snapshots.repositoryUsage(),
      queryFn: snapshotApi.getBackupRepositoryUsage,
      refetchInterval: 30000, // 30秒刷新备份仓库使用情况
      staleTime: 15000, // 15秒
      retry: (failureCount, error: any) => {
        // 如果restic未配置，不要重试
        if (error?.response?.status === 500 && error?.message?.includes('restic')) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  return {
    useGlobalSnapshots,
    useSnapshotsForPath,
    useBackupRepositoryUsage, // 备份仓库使用情况 (快照模块的独立接口)
  };
};

