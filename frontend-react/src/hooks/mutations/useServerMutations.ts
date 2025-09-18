import { serverApi } from "@/hooks/api/serverApi";
import { queryKeys } from "@/utils/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { message } from "antd";

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
      }) => {
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
            // First remove the server
            const result = await serverApi.serverOperation(serverId, "remove");

            // Then try to delete the restart schedule (if it exists)
            try {
              await serverApi.deleteRestartSchedule(serverId);
            } catch (scheduleError) {
              // Ignore errors if restart schedule doesn't exist or deletion fails
              console.warn(`Failed to delete restart schedule for server ${serverId}:`, scheduleError);
            }

            return result;
          default:
            throw new Error(`Unknown action: ${action}`);
        }
      },
      onSuccess: (_, { action, serverId }) => {
        message.success(`服务器 ${serverId} ${action} 操作完成`);

        // 延迟1秒后触发所有相关数据的重新更新
        setTimeout(() => {
          // 失效单个服务器的所有相关缓存
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverInfos.detail(serverId),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverStatuses.detail(serverId),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverRuntimes.detail(serverId),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.players.online(serverId),
          });

          // 失效服务器列表和概览数据，确保整体状态更新
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverInfos.lists(),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverStatuses.all,
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverRuntimes.all,
          });
          queryClient.invalidateQueries({ queryKey: queryKeys.overview() });

          // 失效系统信息，因为服务器状态变化可能影响系统资源使用
          queryClient.invalidateQueries({ queryKey: queryKeys.system.info() });

          // 失效兼容的servers查询
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });

          // 如果是删除操作，也要失效重启计划查询
          if (action === 'remove') {
            queryClient.invalidateQueries({
              queryKey: queryKeys.restartSchedule.detail(serverId),
            });
          }
        }, 1000);
      },
      onError: (error: Error, { action, serverId }) => {
        message.error(
          `服务器 ${serverId} ${action} 操作失败: ${error.message}`
        );
      },
    });
  };

  // RCON命令执行
  const useRconCommand = (serverId: string) => {
    return useMutation({
      mutationFn: async (command: string) => {
        return serverApi.sendRconCommand(serverId, command);
      },
      onSuccess: (result, command) => {
        message.success(`命令执行成功: ${command}`);
        console.log("RCON结果:", result);

        // 如果是可能影响玩家状态的命令，刷新玩家列表
        if (
          ["list", "kick", "ban", "op", "deop"].some((cmd) =>
            command.startsWith(cmd)
          )
        ) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.players.online(serverId),
          });
        }
      },
      onError: (error: Error, command) => {
        message.error(`命令执行失败: ${command} - ${error.message}`);
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
        message.success(`服务器 ${serverId} compose 配置更新成功`);

        // 延迟1秒后失效相关缓存
        setTimeout(() => {
          // 失效compose文件缓存
          queryClient.invalidateQueries({
            queryKey: queryKeys.compose.detail(serverId),
          });

          // 失效服务器信息缓存（compose配置变化可能影响服务器信息）
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverInfos.detail(serverId),
          });

          // 失效状态和运行时数据（服务器可能重启）
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverStatuses.detail(serverId),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverRuntimes.detail(serverId),
          });

          // 失效服务器列表
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });
        }, 1000);
      },
      onError: (error: Error) => {
        message.error(`compose 配置更新失败: ${error.message}`);
      },
    });
  };

  // 服务器数据填充
  const usePopulateServer = () => {
    return useMutation({
      mutationFn: async ({ serverId, archiveFilename }: { serverId: string; archiveFilename: string }) => {
        return serverApi.populateServer(serverId, archiveFilename);
      },
      onSuccess: (data, { serverId }) => {
        message.success(data.message || `服务器 ${serverId} 数据填充完成`);

        // 延迟1秒后失效相关缓存
        setTimeout(() => {
          // 失效服务器信息缓存
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverInfos.detail(serverId),
          });

          // 失效磁盘使用情况缓存（数据填充会改变磁盘使用）
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverDiskUsage.detail(serverId),
          });

          // 失效服务器列表
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });
        }, 1000);
      },
      onError: (error: Error, { serverId }) => {
        message.error(`服务器 ${serverId} 数据填充失败: ${error.message}`);
      },
    });
  };

  // 创建新服务器
  const useCreateServer = () => {
    return useMutation({
      mutationFn: async ({ serverId, yamlContent }: { serverId: string; yamlContent: string }) => {
        return serverApi.createServer(serverId, { yaml_content: yamlContent });
      },
      onSuccess: (_, { serverId }) => {
        message.success(`服务器 "${serverId}" 创建成功!`);

        // 延迟1秒后失效相关缓存
        setTimeout(() => {
          // 失效服务器列表
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() });
          queryClient.invalidateQueries({
            queryKey: queryKeys.serverInfos.lists(),
          });

          // 失效概览数据
          queryClient.invalidateQueries({ queryKey: queryKeys.overview() });
        }, 1000);
      },
      onError: (error: Error, { serverId }) => {
        message.error(`创建服务器 "${serverId}" 失败: ${error.message}`);
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
      onSuccess: (data, { serverId }) => {
        message.success(`服务器 "${serverId}" 重启计划配置成功`);

        // 失效重启计划相关查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.restartSchedule.detail(serverId),
        });
      },
      onError: (error: Error, { serverId }) => {
        message.error(`配置服务器 "${serverId}" 重启计划失败: ${error.message}`);
      },
    });
  };

  // 删除重启计划
  const useDeleteRestartSchedule = () => {
    return useMutation({
      mutationFn: async (serverId: string) => {
        return serverApi.deleteRestartSchedule(serverId);
      },
      onSuccess: (_, serverId) => {
        message.success(`服务器 "${serverId}" 重启计划已删除`);

        // 失效重启计划相关查询
        queryClient.invalidateQueries({
          queryKey: queryKeys.restartSchedule.detail(serverId),
        });
      },
      onError: (error: Error, serverId) => {
        message.error(`删除服务器 "${serverId}" 重启计划失败: ${error.message}`);
      },
    });
  };

  return {
    useServerOperation,
    useRconCommand,
    useUpdateCompose,
    usePopulateServer,
    useCreateServer,
    useCreateOrUpdateRestartSchedule,
    useDeleteRestartSchedule,
  };
};
