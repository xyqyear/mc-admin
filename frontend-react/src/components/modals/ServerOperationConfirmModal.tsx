import { Modal } from 'antd'

export interface ServerOperationConfirmModalProps {
  operation: 'stop' | 'restart' | 'down' | 'remove'
  serverName: string
  serverId: string
  onConfirm: (operation: string, serverId: string) => void
}

export const useServerOperationConfirm = () => {
  const showConfirm = ({ operation, serverName, serverId, onConfirm }: ServerOperationConfirmModalProps) => {
    const confirmConfigs = {
      stop: {
        title: '确认停止',
        content: `确定要停止服务器 "${serverName}" 吗？这将断开所有玩家连接。`,
        okText: '确认停止',
        okType: 'primary' as const
      },
      restart: {
        title: '确认重启',
        content: `确定要重启服务器 "${serverName}" 吗？这将暂时断开所有玩家连接。`,
        okText: '确认重启',
        okType: 'primary' as const
      },
      down: {
        title: '确认下线',
        content: `确定要下线服务器 "${serverName}" 吗？这将停止服务器并清理资源。`,
        okText: '确认下线',
        okType: 'primary' as const
      },
      remove: {
        title: '确认删除',
        content: `确定要删除服务器 "${serverName}" 吗？此操作无法撤销。`,
        okText: '确认删除',
        okType: 'danger' as const
      }
    }

    const config = confirmConfigs[operation]
    if (config) {
      Modal.confirm({
        ...config,
        cancelText: '取消',
        onOk: () => {
          onConfirm(operation, serverId)
        }
      })
    }
  }

  return { showConfirm }
}