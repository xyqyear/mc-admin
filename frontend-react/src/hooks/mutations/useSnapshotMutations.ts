import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  snapshotApi,
  type CreateSnapshotResponse,
  type RestoreSnapshotResponse,
  type DeleteSnapshotResponse
} from "@/hooks/api/snapshotApi";
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

        // 刷新所有快照相关查询（包含仓库占用）
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  // 创建文件/文件夹快照
  const useCreateSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.createSnapshot,
      onSuccess: (data: CreateSnapshotResponse) => {
        message.success(`快照创建成功: ${data.snapshot.short_id}`);

        // 刷新所有快照相关查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  // 恢复快照
  const useRestoreSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.restoreSnapshot,
      onSuccess: (data: RestoreSnapshotResponse) => {
        message.success(data.message);

        // 刷新文件列表和快照列表
        queryClient.invalidateQueries({
          queryKey: queryKeys.files.all,
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`快照恢复失败: ${errorDetail}`);
      },
    });
  };

  // 预览快照恢复
  const usePreviewRestore = () => {
    return useMutation({
      mutationFn: snapshotApi.previewRestore,
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`预览失败: ${errorDetail}`);
      },
    });
  };

  // 删除快照
  const useDeleteSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.deleteSnapshot,
      onSuccess: (data: DeleteSnapshotResponse) => {
        message.success(data.message);

        // 刷新所有快照相关查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`快照删除失败: ${errorDetail}`);
      },
    });
  };

  // 解锁仓库
  const useUnlockRepository = () => {
    return useMutation({
      mutationFn: snapshotApi.unlockRepository,
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        message.error(`仓库解锁失败: ${errorDetail}`);
      },
    });
  };

  return {
    useCreateGlobalSnapshot,
    useCreateSnapshot,
    useRestoreSnapshot,
    usePreviewRestore,
    useDeleteSnapshot,
    useUnlockRepository,
  };
};
