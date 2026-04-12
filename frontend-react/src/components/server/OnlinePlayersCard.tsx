import React from 'react';
import { User, Clock } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useServerOnlinePlayers } from '@/hooks/queries/base/usePlayerQueries';
import { MCAvatar } from '@/components/players/MCAvatar';

interface OnlinePlayersCardProps {
  serverId: string;
  isHealthy: boolean;
  className?: string;
}

const formatDuration = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}小时 ${minutes}分钟`;
  }
  return `${minutes}分钟`;
};

export const OnlinePlayersCard: React.FC<OnlinePlayersCardProps> = ({
  serverId,
  isHealthy,
  className
}) => {
  const { data: onlinePlayers, isLoading } = useServerOnlinePlayers(serverId);

  if (!isHealthy || !onlinePlayers || onlinePlayers.length === 0) {
    return null;
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          <div className="flex items-center gap-2">
            <User className="h-4 w-4" />
            <span>在线玩家</span>
            <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">
              {onlinePlayers.length} 人
            </Badge>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? null : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {onlinePlayers.map(player => (
              <div
                key={player.player_db_id}
                className="flex items-center space-x-3 p-3 bg-muted/50 rounded-lg hover:bg-muted transition-colors"
              >
                <MCAvatar
                  avatarBase64={player.avatar_base64}
                  size={48}
                  playerName={player.current_name}
                />

                <div className="flex-1 min-w-0">
                  <div className="font-medium text-base truncate" title={player.current_name}>
                    {player.current_name}
                  </div>
                  <div
                    className="text-sm text-muted-foreground flex items-center space-x-1 cursor-default"
                    title={`加入时间: ${new Date(player.joined_at).toLocaleString('zh-CN')}`}
                  >
                    <Clock className="h-3 w-3" />
                    <span>{formatDuration(player.session_duration_seconds)}</span>
                  </div>
                </div>

                <Badge className="bg-green-100 text-green-800 hover:bg-green-100 shrink-0">
                  在线
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default OnlinePlayersCard;
