import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { User } from 'lucide-react';

interface ServerPlayersCardProps {
  players?: string[];
  isHealthy: boolean;
  className?: string;
}

export const ServerPlayersCard: React.FC<ServerPlayersCardProps> = ({
  players,
  isHealthy,
  className
}) => {
  if (!isHealthy || !players || players.length === 0) {
    return null;
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">在线玩家 ({players.length})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {players.map(player => (
            <div key={player} className="flex items-center space-x-3 p-3 bg-muted/50 rounded-lg">
              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center">
                <User className="h-4 w-4 text-white" />
              </div>
              <div>
                <div className="font-medium">{player}</div>
                <div className="text-sm text-muted-foreground">在线</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default ServerPlayersCard;
