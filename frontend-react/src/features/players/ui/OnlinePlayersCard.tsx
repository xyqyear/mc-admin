import { formatDuration } from '@/shared/utils/formatUtils';
import React, { useState } from 'react';
import { User, Clock } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/shared/ui/card';
import { StatusBadge } from '@/shared/components/StatusBadge';
import { useServerOnlinePlayers } from '@/features/players/queries';
import { MCAvatar } from '@/features/players/ui/MCAvatar';
import { PlayerDetailDialog } from './PlayerDetailDialog';

interface OnlinePlayersCardProps {
  serverId: string;
  isHealthy: boolean;
  className?: string;
}

export const OnlinePlayersCard: React.FC<OnlinePlayersCardProps> = ({
  serverId,
  isHealthy,
  className
}) => {
  const { data: onlinePlayers, isLoading } = useServerOnlinePlayers(serverId);
  const [selectedUUID, setSelectedUUID] = useState<string | null>(null);
  const showPlayers = isHealthy && !!onlinePlayers?.length;

  return (
    <>
    {showPlayers && <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          <div className="flex items-center gap-2">
            <User className="h-4 w-4" />
            <span>在线玩家</span>
            <StatusBadge tone="info">{onlinePlayers.length} 人</StatusBadge>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? null : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {onlinePlayers?.map(player => (
              <button
                type="button"
                key={player.player_db_id}
                aria-label={`查看 ${player.current_name} 的玩家详情`}
                onClick={() => setSelectedUUID(player.uuid)}
                className="flex items-center space-x-3 p-3 bg-muted/50 rounded-lg hover:bg-muted transition-colors text-left cursor-pointer focus-visible:outline-2 focus-visible:outline-ring"
              >
                <MCAvatar
                  avatarBase64={player.avatar_base64}
                  size={48}
                  playerName={player.current_name}
                />

                <span className="flex-1 min-w-0">
                  <span className="block font-medium text-base truncate" title={player.current_name}>
                    {player.current_name}
                  </span>
                  <span
                    className="text-sm text-muted-foreground flex items-center space-x-1 cursor-default"
                    title={`加入时间: ${new Date(player.joined_at).toLocaleString('zh-CN')}`}
                  >
                    <Clock className="h-3 w-3" />
                    <span>{formatDuration(player.session_duration_seconds, false)}</span>
                  </span>
                </span>

                <StatusBadge tone="success" className="shrink-0">
                  在线
                </StatusBadge>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>}
    {selectedUUID && <PlayerDetailDialog key={selectedUUID} uuid={selectedUUID} open onClose={() => setSelectedUUID(null)} />}
    </>
  );
};

export default OnlinePlayersCard;
