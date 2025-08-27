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
          default:
            throw new Error(`Unknown action: ${action}`)
        }
      },
      onSuccess: (_, { action, serverId }) => {
        message.success(`服务器 ${serverId} ${action} 操作完成`)
        
        // 智能缓存失效
        queryClient.invalidateQueries({ queryKey: queryKeys.serverStatuses.detail(serverId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.serverRuntimes.detail(serverId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.players.online(serverId) })
        
        // 如果是start操作，可能需要更新整体列表
        if (action === 'start') {
          queryClient.invalidateQueries({ queryKey: queryKeys.serverInfos.lists() })
        }
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
