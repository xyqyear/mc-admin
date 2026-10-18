import { Link } from 'react-router'
import { Badge } from '@/shared/ui/badge'

interface ServerNameTagProps {
  serverId: string
  maxLength?: number
}

export const ServerNameTag = ({ serverId, maxLength }: ServerNameTagProps) => {
  const needsTruncate = maxLength && serverId.length > maxLength
  const displayText = needsTruncate
    ? `${serverId.slice(0, maxLength)}...`
    : serverId

  return (
    <Badge
      variant="secondary"
      className="cursor-pointer hover:bg-secondary/80"
      render={<Link to={`/server/${serverId}`} onClick={(event) => event.stopPropagation()} />}
      title={serverId}
    >
      {displayText}
    </Badge>
  )
}

export default ServerNameTag
