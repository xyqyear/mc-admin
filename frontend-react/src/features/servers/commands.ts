import { useState } from 'react';
import type { RestartScheduleRequest } from '@/features/servers/contracts';
import { waitForTaskResult } from '@/features/tasks/commands';
import { taskApi } from '@/features/tasks/api';
import type { ApiError } from '@/shared/http/api';
import { serverApi } from "@/features/servers/api";
import { taskQueryKeys } from "@/features/tasks/queries";
import type {
  CreateServerResult,
  RemoveServerResult,
  SyncRequest,
  SyncResult,
} from "@/features/servers/lifecycleContracts";
import { queryKeys } from "@/shared/http/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

export const useServerMutations = () => {
  const queryClient = useQueryClient();

  const useServerOperation = () => {
    const [taskId, setTaskId] = useState<string | null>(null);
    const mutation = useMutation({
      mutationFn: async ({
        action,
        serverId,
      }: {
        action: string;
        serverId: string;
      }): Promise<unknown> => {
        setTaskId(null);
        const accepted = await serverApi.serverOperation(serverId, action);
        setTaskId(accepted.task_id);
        return waitForTaskResult(queryClient, accepted);
      },
      onSuccess: (data, { action, serverId }) => {
        if (action === "remove") {
          const result = data as RemoveServerResult;
          const cronCount = result.cancelled_restart_cronjob_ids.length;
          toast.success(
            cronCount > 0
              ? `服务器 ${serverId} 删除完成（同时取消了 ${cronCount} 个重启计划）`
              : `服务器 ${serverId} 删除完成`,
          );
        } else {
          toast.success(`服务器 ${serverId} ${action} 操作完成`);
        }
      },
      onError: (error: Error, { action, serverId }) => {
        toast.error(
          `服务器 ${serverId} ${action} 操作失败: ${error.message}`
        );
      },
    });
    return { ...mutation, taskId };
  };

  // Returns task_id; populate progress is polled via the task API.
  const usePopulateServer = () => {
    return useMutation({
      mutationFn: async ({ serverId, archiveFilename }: { serverId: string; archiveFilename: string }) => {
        return serverApi.populateServer(serverId, archiveFilename);
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
        queryClient.invalidateQueries({ queryKey: queryKeys.operations.all });
      },
      onError: (error: Error, { serverId }) => {
        toast.error(`服务器 ${serverId} 数据填充失败: ${error.message}`);
      },
    });
  };

  const useCreateServer = () => {
    return useMutation({
      mutationFn: async ({
        serverId,
        yamlContent,
        templateId,
        variableValues,
        restartSchedule,
      }: {
        serverId: string;
        yamlContent?: string;
        templateId?: number;
        variableValues?: Record<string, unknown>;
        restartSchedule?: RestartScheduleRequest | null;
      }): Promise<CreateServerResult> => {
        const accepted = await serverApi.createServer(serverId, {
          yaml_content: yamlContent,
          template_id: templateId,
          variable_values: variableValues,
          restart_schedule: restartSchedule ?? undefined,
        });
        return waitForTaskResult<CreateServerResult>(queryClient, accepted);
      },
      onSuccess: (result, { serverId }) => {
        toast.success(
          result.restart_cronjob_id
            ? `服务器 "${serverId}" 创建成功并已配置重启计划`
            : `服务器 "${serverId}" 创建成功!`,
        );

        queryClient.invalidateQueries({ queryKey: queryKeys.servers() });
        if (result.restart_cronjob_id) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.restartSchedule.detail(serverId),
          });
          queryClient.invalidateQueries({ queryKey: queryKeys.cron.all });
        }
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.all });
      },
      onError: (error: Error, { serverId }) => {
        toast.error(`创建服务器 "${serverId}" 失败: ${error.message}`);
      },
    });
  };

  const useSyncServers = () => {
    return useMutation({
      mutationFn: async (request: SyncRequest = {}): Promise<SyncResult> => {
        if (request.dry_run) {
          const active = (await taskApi.getActiveTasks()).find(task => task.taskType === 'server_sync');
          if (active) return waitForTaskResult<SyncResult>(queryClient, { task_id: active.taskId });
        }
        try {
          return await waitForTaskResult<SyncResult>(queryClient, await serverApi.syncServers(request));
        } catch (error) {
          const detail = (error as ApiError).detail as { task_id?: string } | undefined;
          if (request.dry_run && (error as ApiError).code === 'task_conflict' && detail?.task_id) {
            return waitForTaskResult<SyncResult>(queryClient, { task_id: detail.task_id });
          }
          throw error;
        }
      },
      onSuccess: (result) => {
        if (result.applied) {
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });
          queryClient.invalidateQueries({ queryKey: queryKeys.dns.all });
          queryClient.invalidateQueries({ queryKey: queryKeys.cron.all });
        }
      },
    });
  };

  const useCreateOrUpdateRestartSchedule = () => {
    return useMutation({
      mutationFn: async ({
        serverId,
        customCron
      }: {
        serverId: string;
        customCron?: string;
      }) => {
        return serverApi.createOrUpdateRestartSchedule(serverId, customCron);
      },
      onSuccess: (_, { serverId }) => {
        toast.success(`服务器 "${serverId}" 重启计划配置成功`);

        queryClient.invalidateQueries({
          queryKey: queryKeys.restartSchedule.detail(serverId),
        });

        queryClient.invalidateQueries({
          queryKey: queryKeys.cron.all,
        });
      },
      onError: (error: Error, { serverId }) => {
        toast.error(`配置服务器 "${serverId}" 重启计划失败: ${error.message}`);
      },
    });
  };

  const useDeleteRestartSchedule = (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    return useMutation({
      mutationFn: async (serverId: string) => {
        return serverApi.deleteRestartSchedule(serverId);
      },
      onSuccess: (_, serverId) => {
        if (!silent) {
          toast.success(`服务器 "${serverId}" 重启计划已删除`);
        }

        queryClient.invalidateQueries({
          queryKey: queryKeys.restartSchedule.detail(serverId),
        });

        queryClient.invalidateQueries({
          queryKey: queryKeys.cron.all,
        });
      },
      onError: (error: Error, serverId) => {
        if (!silent) {
          toast.error(`删除服务器 "${serverId}" 重启计划失败: ${error.message}`);
        }
      },
    });
  };

  return {
    useServerOperation,
    usePopulateServer,
    useCreateServer,
    useCreateOrUpdateRestartSchedule,
    useDeleteRestartSchedule,
    useSyncServers,
  };
};
