import type { ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { snapshotApi } from "@/features/backups/api";
import type { CreateSnapshotResponse, DeleteSnapshotResponse, UnlockResponse } from '@/features/backups/contracts';
import { queryKeys } from "@/shared/http/api";
import { toast } from "sonner";
import { waitForTaskResult } from '@/features/tasks/commands';
import type { SnapshotScope } from './contracts';
import { useState } from 'react';
import type { BackgroundTask } from '@/features/tasks/contracts';

export { useSnapshotOperation } from './useSnapshotOperation';

export function useCreateSnapshot() {
  const client = useQueryClient();
  const [task, setTask] = useState<BackgroundTask | null>(null);
  const mutation = useMutation({
    mutationFn: async (scope: SnapshotScope) => {
      setTask(null);
      return waitForTaskResult<CreateSnapshotResponse>(client, await snapshotApi.createSnapshot(scope), { onProgress: setTask });
    },
    onSuccess: data => { toast.success(`快照创建成功: ${data.snapshot.short_id}`) },
    onError: (error: Error) => { toast.error(`快照创建失败: ${error.message}`) },
  });
  return { ...mutation, task };
}

export function fileSnapshotScope(serverId: string, paths?: string[]): SnapshotScope {
  return paths?.length
    ? { kind: 'paths', server_id: serverId, paths: paths.map(path => path.replace(/^\/+/, '') || '.') }
    : { kind: 'server', server_id: serverId };
}
export const useDeleteSnapshot = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => waitForTaskResult<DeleteSnapshotResponse>(queryClient, await snapshotApi.deleteSnapshot(id)),
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

export const useUnlockRepository = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => waitForTaskResult<UnlockResponse>(queryClient, await snapshotApi.unlockRepository()),
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


export { useSnapshotPreview } from './useSnapshotPreview'
