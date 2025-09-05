import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { snapshotApi, type Snapshot, type CreateSnapshotResponse } from "@/hooks/api/serverApi";
import { queryKeys } from "@/utils/api";
import { message } from "antd";

export const useSnapshotQueries = () => {
  // 获取所有快照列表
  const useGlobalSnapshots = (options?: UseQueryOptions<Snapshot[]>) => {
    return useQuery({
      queryKey: queryKeys.snapshots.global(),
      queryFn: snapshotApi.getAllSnapshots,
      staleTime: 2 * 60 * 1000, // 2分钟 - 快照列表变化较慢
      refetchInterval: false, // 不自动刷新，手动操作时刷新
      ...options,
    });
  };

  return {
    useGlobalSnapshots,
  };
};

export const useSnapshotMutations = () => {
  const queryClient = useQueryClient();

  // 创建全局快照
  const useCreateGlobalSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.createGlobalSnapshot,
      onSuccess: (data: CreateSnapshotResponse) => {
        message.success(`快照创建成功: ${data.snapshot.short_id}`);
        
        // 刷新快照列表
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.global(),
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  return {
    useCreateGlobalSnapshot,
  };
};