import React from 'react';
import { Card } from 'antd';
import { UserOutlined } from '@ant-design/icons';

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
    <Card title={`在线玩家 (${players.length})`} className={className}>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {players.map(player => (
          <div key={player} className="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg">
            <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center">
              <UserOutlined className="text-white" />
            </div>
            <div>
              <div className="font-medium">{player}</div>
              <div className="text-sm text-gray-500">在线</div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};

export default ServerPlayersCard;