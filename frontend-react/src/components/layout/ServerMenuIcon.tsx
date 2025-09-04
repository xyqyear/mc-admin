import React from 'react'
import { useServerQueries } from '@/hooks/queries/useServerQueries'
import ServerStateIcon from '@/components/overview/ServerStateIcon'
import { DesktopOutlined } from '@ant-design/icons'

interface ServerMenuIconProps {
  serverId: string
}

const ServerMenuIcon: React.FC<ServerMenuIconProps> = ({ serverId }) => {
  const { useServerStatus } = useServerQueries()
  const statusQuery = useServerStatus(serverId)

  // 如果状态加载失败或未加载完成，显示默认图标
  if (statusQuery.isError || !statusQuery.data) {
    return <DesktopOutlined />
  }

  return <ServerStateIcon state={statusQuery.data} />
}

export default ServerMenuIcon