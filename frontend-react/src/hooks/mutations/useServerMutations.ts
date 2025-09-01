import { serverApi } from '@/hooks/api/serverApi'
import { queryKeys } from '@/utils/api'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'

export const useServerMutations = () => {
  const queryClient = useQueryClient()
  
  // 服务器操作基础mutation
  const useServerOperation = () => {
    return useMutation({
      mutationFn: async ({ action, serverId }: { action: string, serverId: string }) => {
        switch (action) {
          case 'start': 
            return serverApi.startServer(serverId)
          case 'stop': 
            return serverApi.stopServer(serverId)
          case 'restart': 
            return serverApi.restartServer(serverId)
          case 'up':
            return serverApi.upServer(serverId)
          case 'down':
            return serverApi.downServer(serverId)
          case 'remove':
            return serverApi.serverOperation(serverId, 'remove')
          default:
            throw new Error(`Unknown action: ${action}`)
        }
      },
      onSuccess: (_, { action, serverId }) => {
        message.success(`服务器 ${serverId} ${action} 操作完成`)
        
        // 延迟1秒后触发所有相关数据的重新更新
        setTimeout(() => {
          // 失效单个服务器的所有相关缓存
          queryClient.invalidateQueries({ queryKey: queryKeys.serverInfos.detail(serverId) })
          queryClient.invalidateQueries({ queryKey: queryKeys.serverStatuses.detail(serverId) })
          queryClient.invalidateQueries({ queryKey: queryKeys.serverRuntimes.detail(serverId) })
          queryClient.invalidateQueries({ queryKey: queryKeys.players.online(serverId) })
          
          // 失效服务器列表和概览数据，确保整体状态更新
          queryClient.invalidateQueries({ queryKey: queryKeys.serverInfos.lists() })
          queryClient.invalidateQueries({ queryKey: queryKeys.serverStatuses.all })
          queryClient.invalidateQueries({ queryKey: queryKeys.serverRuntimes.all })
          queryClient.invalidateQueries({ queryKey: queryKeys.overview() })
          
          // 失效系统信息，因为服务器状态变化可能影响系统资源使用
          queryClient.invalidateQueries({ queryKey: queryKeys.system.info() })
          
          // 失效兼容的servers查询
          queryClient.invalidateQueries({ queryKey: queryKeys.servers() })
        }, 1000)
      },
      onError: (error: Error, { action, serverId }) => {
        message.error(`服务器 ${serverId} ${action} 操作失败: ${error.message}`)
      }
    })
  }
  
  // RCON命令执行
  const useRconCommand = (serverId: string) => {
    return useMutation({
      mutationFn: async (command: string) => {
        return serverApi.sendRconCommand(serverId, command)
      },
      onSuccess: (result, command) => {
        message.success(`命令执行成功: ${command}`)
        console.log('RCON结果:', result)
        
        // 如果是可能影响玩家状态的命令，刷新玩家列表
        if (['list', 'kick', 'ban', 'op', 'deop'].some(cmd => command.startsWith(cmd))) {
          queryClient.invalidateQueries({ queryKey: queryKeys.players.online(serverId) })
        }
      },
      onError: (error: Error, command) => {
        message.error(`命令执行失败: ${command} - ${error.message}`)
      }
    })
  }
  
  return {
    useServerOperation,
    useRconCommand
  }
}
