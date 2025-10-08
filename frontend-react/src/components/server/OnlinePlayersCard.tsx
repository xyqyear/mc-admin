import React from 'react';
import { Card, Tag, Space, Tooltip } from 'antd';
import { UserOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useServerOnlinePlayers } from '@/hooks/queries/base/usePlayerQueries';
import { MCAvatar } from '@/components/players/MCAvatar';

interface OnlinePlayersCardProps {
  serverId: string;
  isHealthy: boolean;
  className?: string;
}

// 格式化游戏时长
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
  // 使用新的玩家查询hook
  const { data: onlinePlayers, isLoading } = useServerOnlinePlayers(serverId);

  // 如果服务器不健康或没有在线玩家，不显示卡片
  if (!isHealthy || !onlinePlayers || onlinePlayers.length === 0) {
    return null;
  }

  return (
    <Card
      title={
        <Space>
          <UserOutlined />
          <span>在线玩家</span>
          <Tag color="blue">{onlinePlayers.length} 人</Tag>
        </Space>
      }
      className={className}
      loading={isLoading}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {onlinePlayers.map(player => (
          <div
            key={player.player_db_id}
            className="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
          >
            {/* 玩家头像 */}
            <MCAvatar
              avatarBase64={player.avatar_base64}
              size={48}
              playerName={player.current_name}
            />

            {/* 玩家信息 */}
            <div className="flex-1 min-w-0">
              <div className="font-medium text-base truncate" title={player.current_name}>
                {player.current_name}
              </div>
              <Tooltip title={`加入时间: ${new Date(player.joined_at).toLocaleString('zh-CN')}`}>
                <div className="text-sm text-gray-500 flex items-center space-x-1">
                  <ClockCircleOutlined />
                  <span>{formatDuration(player.session_duration_seconds)}</span>
                </div>
              </Tooltip>
            </div>

            {/* 在线状态标签 */}
            <Tag color="success" className="flex-shrink-0">
              在线
            </Tag>
          </div>
        ))}
      </div>
    </Card>
  );
};

export default OnlinePlayersCard;
