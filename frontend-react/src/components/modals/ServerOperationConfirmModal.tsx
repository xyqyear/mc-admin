import { useConfirm } from '@/hooks/useConfirm'

export interface ServerOperationConfirmModalProps {
  operation: 'stop' | 'restart' | 'down' | 'remove'
  serverName: string
  serverId: string
  onConfirm: (operation: string, serverId: string) => void
}

const confirmConfigs = {
  stop: {
    title: '确认停止',
    description: '确定要停止服务器 "{name}" 吗？这将断开所有玩家连接。',
    confirmText: '确认停止',
    variant: 'default' as const,
  },
  restart: {
    title: '确认重启',
    description: '确定要重启服务器 "{name}" 吗？这将暂时断开所有玩家连接。',
    confirmText: '确认重启',
    variant: 'default' as const,
  },
  down: {
    title: '确认下线',
    description: '确定要下线服务器 "{name}" 吗？这将停止服务器并清理资源。',
    confirmText: '确认下线',
    variant: 'default' as const,
  },
  remove: {
    title: '确认删除',
    description: '确定要删除服务器 "{name}" 吗？此操作无法撤销。',
    confirmText: '确认删除',
    variant: 'destructive' as const,
  },
}

export const useServerOperationConfirm = () => {
  const { confirm, ConfirmDialog } = useConfirm()

  const showConfirm = ({ operation, serverName, serverId, onConfirm }: ServerOperationConfirmModalProps) => {
    const config = confirmConfigs[operation]
    if (config) {
      confirm({
        title: config.title,
        description: config.description.replace('{name}', serverName),
        confirmText: config.confirmText,
        cancelText: '取消',
        variant: config.variant,
        onConfirm: () => {
          onConfirm(operation, serverId)
        },
      })
    }
  }

  return { showConfirm, ConfirmDialog }
}
