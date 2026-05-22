import React from 'react'
import { User } from 'lucide-react'

import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

interface MCAvatarProps {
  avatarBase64?: string | null;
  size?: number;
  className?: string;
  playerName?: string;
}

export const MCAvatar: React.FC<MCAvatarProps> = ({
  avatarBase64,
  size = 48,
  className = '',
  playerName = '玩家'
}) => {
  const hasAvatar = avatarBase64 && avatarBase64.trim() !== ''
  const fallbackText = playerName.trim().slice(0, 1).toUpperCase()

  return (
    <Avatar
      className={cn('rounded-sm after:rounded-sm', className)}
      style={{
        width: size,
        height: size,
        minWidth: size,
        minHeight: size
      }}
    >
      {hasAvatar && (
        <AvatarImage
          src={`data:image/png;base64,${avatarBase64}`}
          alt={`${playerName}的头像`}
          className="rounded-sm"
          style={{
            imageRendering: 'pixelated',
          }}
        />
      )}
      <AvatarFallback className="rounded-sm">
        {fallbackText ? (
          <span className="text-xs font-medium">{fallbackText}</span>
        ) : (
          <User style={{ width: size * 0.45, height: size * 0.45 }} />
        )}
      </AvatarFallback>
    </Avatar>
  )
}

export default MCAvatar
