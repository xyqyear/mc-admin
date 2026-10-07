import type { ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { snapshotApi } from "@/features/backups/api";
import type { CreateSnapshotResponse, DeleteSnapshotResponse, UnlockResponse } from '@/features/backups/contracts';
import { queryKeys } from "@/shared/http/api";
import { toast } from "sonner";
import { waitForTaskResult } from '@/features/tasks/commands';
import type { CreateSnapshotRequest, PathsScope, SnapshotScope } from './contracts';
import { useState } from 'react';
import type { BackgroundTask } from '@/features/tasks/contracts';

export { useSnapshotOperation } from './useSnapshotOperation';

export function useCreateSnapshot() {
  const client = useQueryClient();
  const [task, setTask] = useState<BackgroundTask | null>(null);
  const mutation = useMutation({
    mutationFn: async (request: SnapshotScope | CreateSnapshotRequest) => {
      setTask(null);
      const { scope, note } = 'scope' in request ? request : { scope: request, note: undefined };
      return waitForTaskResult<CreateSnapshotResponse>(client, await snapshotApi.createSnapshot(scope, note), { onProgress: setTask });
    },
    onSuccess: data => {
      if (data.note_warning) toast.warning(`快照已创建: ${data.snapshot.short_id}`, { description: data.note_warning });
      else toast.success(`快照创建成功: ${data.snapshot.short_id}`);
    },
    onError: (error: Error) => { toast.error(`快照创建失败: ${error.message}`) },
  });
  return { ...mutation, task };
}

export function useUpdateSnapshotNote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ snapshotId, note }: { snapshotId: string; note: string }) => snapshotApi.updateNote(snapshotId, note),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.snapshots.all });
      toast.success('快照备注已保存');
    },
    onError: (error: Error) => toast.error(`备注保存失败: ${error.message}`),
  });
}

export function fileSnapshotScope(serverId: string, paths: string[]): PathsScope {
  return { kind: 'paths', server_id: serverId, paths: paths.map(path => path.replace(/^\/+/, '') || '.') };
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
