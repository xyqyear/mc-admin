import React from 'react'
import { Monitor } from 'lucide-react'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import ServerStateIcon from '@/components/overview/ServerStateIcon'

interface ServerMenuIconProps {
  serverId: string
}

const ServerMenuIcon: React.FC<ServerMenuIconProps> = ({ serverId }) => {
  const { useServerStatus } = useServerQueries()
  const statusQuery = useServerStatus(serverId)

  if (statusQuery.isError || !statusQuery.data) {
    return <Monitor className="h-4 w-4" />
  }

  return <ServerStateIcon state={statusQuery.data} />
}

export default ServerMenuIcon
