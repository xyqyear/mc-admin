import type { ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { snapshotApi } from "@/features/backups/api";
import type { CreateSnapshotResponse, DeleteSnapshotResponse } from '@/features/backups/contracts';
import { queryKeys } from "@/shared/http/api";
import { toast } from "sonner";
import { waitForTaskResult } from '@/features/tasks/commands';
import type { SnapshotScope } from './contracts';

export { useSnapshotOperation } from './useSnapshotOperation';

export async function createSnapshot(client: QueryClient, scope: SnapshotScope) {
  return waitForTaskResult<CreateSnapshotResponse>(client, await snapshotApi.createSnapshot(scope));
}

export function fileSnapshotScope(serverId: string, paths?: string[]): SnapshotScope {
  return paths?.length
    ? { kind: 'paths', server_id: serverId, paths: paths.map(path => path.replace(/^\/+/, '') || '.') }
    : { kind: 'server', server_id: serverId };
}

export const useSnapshotMutations = () => {
  const queryClient = useQueryClient();

  const useCreateGlobalSnapshot = () => {
    return useMutation({
      mutationFn: () => createSnapshot(queryClient, { kind: 'global' }),
      onSuccess: (data: CreateSnapshotResponse) => {
        toast.success(`快照创建成功: ${data.snapshot.short_id}`);

        // Snapshot creation also affects repository usage; invalidate the whole tree.
        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: ApiError) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  const useCreateSnapshot = () => {
    return useMutation({
      mutationFn: (params: { server_id: string; paths?: string[] }) => createSnapshot(queryClient, fileSnapshotScope(params.server_id, params.paths)),
      onSuccess: (data: CreateSnapshotResponse) => {
        toast.success(`快照创建成功: ${data.snapshot.short_id}`);

        queryClient.invalidateQueries({
          queryKey: queryKeys.snapshots.all,
        });
      },
      onError: (error: ApiError) => {
        const errorDetail = error?.message || "未知错误";
        toast.error(`快照创建失败: ${errorDetail}`);
      },
    });
  };

  const usePreviewRestore = () => {
    return useMutation({
      mutationFn: snapshotApi.previewRestore,
      onError: (error: ApiError) => {
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
      onError: (error: ApiError) => {
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
      onError: (error: ApiError) => {
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
