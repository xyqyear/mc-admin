import { serverApi } from "@/hooks/api/serverApi";
import { taskQueryKeys } from "@/hooks/queries/base/useTaskQueries";
import type {
  CreateServerResult,
  RemoveServerResult,
  RestartScheduleRequest,
  SyncRequest,
  SyncResult,
} from "@/types/lifecycle";
import { queryKeys } from "@/utils/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

export const useServerMutations = () => {
  const queryClient = useQueryClient();

  const useServerOperation = () => {
    return useMutation({
      mutationFn: async ({
        action,
        serverId,
      }: {
        action: string;
        serverId: string;
      }): Promise<unknown> => {
        switch (action) {
          case "start":
            return serverApi.startServer(serverId);
          case "stop":
            return serverApi.stopServer(serverId);
          case "restart":
            return serverApi.restartServer(serverId);
          case "up":
            return serverApi.upServer(serverId);
          case "down":
            return serverApi.downServer(serverId);
          case "remove":
            return serverApi.removeServerFull(serverId);
          default:
            throw new Error(`Unknown action: ${action}`);
        }
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

        // Container state takes a moment to settle after the operation lands;
        // refetching immediately tends to capture the pre-action state.
        setTimeout(() => {
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverInfos.detail(serverId),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverStatuses.all,
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverRuntimes.all,
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.players.serverOnline(serverId),
          });

          // Server lifecycle changes affect host-level resource usage.
          queryClient.invalidateQueries({ queryKey: queryKeys.system.info() });

          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });

          if (action === "remove") {
            queryClient.invalidateQueries({
              queryKey: queryKeys.restartSchedule.detail(serverId),
            });
            queryClient.invalidateQueries({
              queryKey: queryKeys.cron.all,
            });
            queryClient.invalidateQueries({
              queryKey: queryKeys.dns.all,
            });
          }
        }, 1000);
      },
      onError: (error: Error, { action, serverId }) => {
        toast.error(
          `服务器 ${serverId} ${action} 操作失败: ${error.message}`
        );
      },
    });
  };

  const useUpdateCompose = (serverId: string) => {
    return useMutation({
      mutationFn: async (yamlContent: string) => {
        return serverApi.updateComposeFile(serverId, yamlContent);
      },
      onSuccess: () => {
        toast.success(`服务器 ${serverId} compose 配置更新成功`);
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
      },
      onError: (error: Error) => {
        toast.error(`compose 配置更新失败: ${error.message}`);
      },
    });
  };

  // Returns task_id; populate progress is polled via the task API.
  const usePopulateServer = () => {
    return useMutation({
      mutationFn: async ({ serverId, archiveFilename }: { serverId: string; archiveFilename: string }) => {
        return serverApi.populateServer(serverId, archiveFilename);
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
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
        return serverApi.createServer(serverId, {
          yaml_content: yamlContent,
          template_id: templateId,
          variable_values: variableValues,
          restart_schedule: restartSchedule ?? undefined,
        });
      },
      onSuccess: (result, { serverId }) => {
        toast.success(
          result.restart_cronjob_id
            ? `服务器 "${serverId}" 创建成功并已配置重启计划`
            : `服务器 "${serverId}" 创建成功!`,
        );

        // Allow the backend to finish wiring up the new server before refetching.
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });
          if (result.restart_cronjob_id) {
            queryClient.invalidateQueries({
              queryKey: queryKeys.restartSchedule.detail(serverId),
            });
            queryClient.invalidateQueries({ queryKey: queryKeys.cron.all });
          }
          queryClient.invalidateQueries({ queryKey: queryKeys.dns.all });
        }, 1000);
      },
      onError: (error: Error, { serverId }) => {
        toast.error(`创建服务器 "${serverId}" 失败: ${error.message}`);
      },
    });
  };

  const useSyncServers = () => {
    return useMutation({
      mutationFn: async (request: SyncRequest = {}): Promise<SyncResult> => {
        return serverApi.syncServers(request);
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
    useUpdateCompose,
    usePopulateServer,
    useCreateServer,
    useCreateOrUpdateRestartSchedule,
    useDeleteRestartSchedule,
    useSyncServers,
  };
};
