import { useMutation, useQueryClient } from "@tanstack/react-query";
import { snapshotApi, type CreateSnapshotResponse } from "@/hooks/api/snapshotApi";
import { queryKeys } from "@/utils/api";
import { message } from "antd";

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