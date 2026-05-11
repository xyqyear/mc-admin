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

  // 服务器操作基础mutation
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
            // 后端会原子化地取消重启计划、关闭会话、删除目录，并触发 DNS 更新
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

        // 延迟1秒后触发所有相关数据的重新更新
        setTimeout(() => {
          // 失效单个服务器的所有相关缓存
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

          // 失效系统信息，因为服务器状态变化可能影响系统资源使用
          queryClient.invalidateQueries({ queryKey: queryKeys.system.info() });

          // 失效兼容的servers查询
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });

          // 如果是删除操作，也要失效重启计划查询和DNS查询
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

  // Compose文件更新
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

  // 服务器数据填充 (returns task_id for background task tracking)
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

  // 创建新服务器 — 可一次性附带 restart_schedule，
  // 后端会在同一个请求里创建服务器、配置重启计划、并触发 DNS 更新
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

        // 延迟1秒后失效相关缓存
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

  // 文件系统 ↔ 数据库 同步 (OWNER-only)
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

  // 创建或更新重启计划
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

        // 失效重启计划相关查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.restartSchedule.detail(serverId),
        });

        // 失效所有cron查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.cron.all,
        });
      },
      onError: (error: Error, { serverId }) => {
        toast.error(`配置服务器 "${serverId}" 重启计划失败: ${error.message}`);
      },
    });
  };

  // 删除重启计划
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

        // 失效重启计划相关查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.restartSchedule.detail(serverId),
        });

        // 失效所有cron查询
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
