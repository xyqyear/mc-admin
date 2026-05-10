import React from 'react';
import { User } from 'lucide-react';

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
  const hasAvatar = avatarBase64 && avatarBase64.trim() !== '';

  return (
    <div
      className={`inline-flex items-center justify-center shrink-0 bg-gray-200 ${className}`}
      style={{
        width: size,
        height: size,
        minWidth: size,
        minHeight: size
      }}
    >
      {hasAvatar ? (
        <img
          src={`data:image/png;base64,${avatarBase64}`}
          alt={`${playerName}的头像`}
          className="w-full h-full"
          style={{
            imageRendering: 'pixelated',
          }}
        />
      ) : (
        <User
          size={size * 0.5}
          className="text-muted-foreground"
        />
      )}
    </div>
  );
};

export default MCAvatar;
