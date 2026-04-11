import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

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
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            variant="secondary"
            className="cursor-pointer hover:bg-secondary/80"
            onClick={handleClick}
          />
        }
      >
        {displayText}
      </TooltipTrigger>
      <TooltipContent>{serverId}</TooltipContent>
    </Tooltip>
  )
}

export default ServerNameTag
