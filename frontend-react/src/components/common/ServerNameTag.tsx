import React from 'react'
import { useNavigate } from 'react-router'
import { Badge } from '@/components/ui/badge'

interface ServerNameTagProps {
  serverId: string
  maxLength?: number
}

export const ServerNameTag = ({ serverId, maxLength }: ServerNameTagProps) => {
  const navigate = useNavigate()

  const needsTruncate = maxLength && serverId.length > maxLength
  const displayText = needsTruncate
    ? `${serverId.slice(0, maxLength)}...`
    : serverId

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigate(`/server/${serverId}`)
  }

  return (
    <Badge
      variant="secondary"
      className="cursor-pointer hover:bg-secondary/80"
      onClick={handleClick}
      title={serverId}
    >
      {displayText}
    </Badge>
  )
}

export default ServerNameTag
