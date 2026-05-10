import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  snapshotApi,
  type CreateSnapshotResponse,
  type DeleteSnapshotResponse
} from "@/hooks/api/snapshotApi";
import { queryKeys } from "@/utils/api";
import { toast } from "sonner";

export const useSnapshotMutations = () => {
  const queryClient = useQueryClient();

  const useCreateGlobalSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.createGlobalSnapshot,
      onSuccess: (data: CreateSnapshotResponse) => {
        toast.success(`快照创建成功: ${data.snapshot.short_id}`);

        // Snapshot creation also affects repository usage; invalidate the whole tree.
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  const useCreateSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.createSnapshot,
      onSuccess: (data: CreateSnapshotResponse) => {
        toast.success(`快照创建成功: ${data.snapshot.short_id}`);

        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  const usePreviewRestore = () => {
    return useMutation({
      mutationFn: snapshotApi.previewRestore,
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`预览失败: ${errorDetail}`);
      },
    });
  };

  const useDeleteSnapshot = () => {
    return useMutation({
      mutationFn: snapshotApi.deleteSnapshot,
      onSuccess: (data: DeleteSnapshotResponse) => {
        toast.success(data.message);

        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`快照删除失败: ${errorDetail}`);
      },
    });
  };

  const useUnlockRepository = () => {
    return useMutation({
      mutationFn: snapshotApi.unlockRepository,
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.locks(),
        });
      },
      onError: (error: any) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`仓库解锁失败: ${errorDetail}`);
      },
    });
  };

  return {
    useCreateGlobalSnapshot,
    useCreateSnapshot,
    usePreviewRestore,
    useDeleteSnapshot,
    useUnlockRepository,
  };
};
