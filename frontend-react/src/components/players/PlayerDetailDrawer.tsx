import React, { useState } from 'react';
import {
  Drawer,
  Tabs,
  Tag,
  Descriptions,
  Card,
  Space,
  Statistic,
  Row,
  Col,
  Table,
  Empty,
  Typography,
  Image,
  Button,
  message
} from 'antd';
import {
  UserOutlined,
  ClockCircleOutlined,
  MessageOutlined,
  TrophyOutlined,
  CalendarOutlined,
  GlobalOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import type { TableProps } from 'antd';
import {
  usePlayerByUUID,
  usePlayerSessions,
  usePlayerSessionStats,
  usePlayerChat,
  usePlayerAchievements
} from '@/hooks/queries/base/usePlayerQueries';
import type {
  SessionInfo,
  ChatMessageInfo,
  AchievementInfo
} from '@/hooks/api/playerApi';
import { playerApi } from '@/hooks/api/playerApi';
import LoadingSpinner from '@/components/layout/LoadingSpinner';
import { MCAvatar } from '@/components/players/MCAvatar';
import { formatUUID } from '@/utils/formatUtils';

const { Text } = Typography;

interface PlayerDetailDrawerProps {
  uuid: string | null;
  open: boolean;
  onClose: () => void;
}

export const PlayerDetailDrawer: React.FC<PlayerDetailDrawerProps> = ({
  uuid,
  open,
  onClose
}) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [refreshingSkin, setRefreshingSkin] = useState(false);

  // 获取玩家详情
  const { data: player, isLoading: playerLoading } = usePlayerByUUID(uuid);

  // 获取玩家会话（最近50条）
  const { data: sessions = [], isLoading: sessionsLoading } = usePlayerSessions(
    player?.player_db_id || null,
    { limit: 50 }
  );

  // 获取会话统计
  const { data: sessionStats } = usePlayerSessionStats(
    player?.player_db_id || null,
    'all'
  );

  // 获取聊天记录（最近100条）
  const { data: chatMessages = [], isLoading: chatLoading } = usePlayerChat(
    player?.player_db_id || null,
    { limit: 100 }
  );

  // 获取成就列表
  const { data: achievements = [], isLoading: achievementsLoading } = usePlayerAchievements(
    player?.player_db_id || null
  );

  // 格式化时长
  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (hours >= 24) {
      const days = Math.floor(hours / 24);
      const remainingHours = hours % 24;
      return `${days}天 ${remainingHours}小时`;
    }
    if (hours > 0) {
      return `${hours}小时 ${minutes}分钟`;
    }
    return `${minutes}分钟`;
  };

  // 刷新皮肤
  const handleRefreshSkin = async () => {
    if (!player) return;

    setRefreshingSkin(true);
    try {
      await playerApi.refreshPlayerSkin(player.player_db_id);
      message.success('皮肤刷新请求已发送，请稍后查看');
    } catch (error: any) {
      message.error(`刷新失败: ${error.message || '未知错误'}`);
    } finally {
      setRefreshingSkin(false);
    }
  };

  // 会话列表列定义
  const sessionColumns: TableProps<SessionInfo>['columns'] = [
    {
      title: '服务器',
      dataIndex: 'server_id',
      key: 'server_id',
      width: 150,
      render: (serverId: string) => (
        <Tag color="blue">{serverId}</Tag>
      )
    },
    {
      title: '加入时间',
      dataIndex: 'joined_at',
      key: 'joined_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN')
    },
    {
      title: '离开时间',
      dataIndex: 'left_at',
      key: 'left_at',
      width: 180,
      render: (date: string | null) =>
        date ? new Date(date).toLocaleString('zh-CN') : <Tag color="success">在线中</Tag>
    },
    {
      title: '游戏时长',
      dataIndex: 'duration_seconds',
      key: 'duration',
      width: 120,
      render: (seconds: number | null) =>
        seconds !== null ? formatDuration(seconds) : '-'
    }
  ];

  // 聊天记录列定义
  const chatColumns: TableProps<ChatMessageInfo>['columns'] = [
    {
      title: '时间',
      dataIndex: 'sent_at',
      key: 'sent_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN')
    },
    {
      title: '服务器',
      dataIndex: 'server_id',
      key: 'server_id',
      width: 120,
      render: (serverId: string) => <Tag color="blue">{serverId}</Tag>
    },
    {
      title: '消息内容',
      dataIndex: 'message_text',
      key: 'message',
      ellipsis: true
    }
  ];

  // 成就列定义
  const achievementColumns: TableProps<AchievementInfo>['columns'] = [
    {
      title: '成就名称',
      dataIndex: 'achievement_name',
      key: 'achievement_name',
      ellipsis: true
    },
    {
      title: '服务器',
      dataIndex: 'server_id',
      key: 'server_id',
      width: 120,
      render: (serverId: string) => <Tag color="blue">{serverId}</Tag>
    },
    {
      title: '获得时间',
      dataIndex: 'earned_at',
      key: 'earned_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN')
    }
  ];

  if (!open) return null;

  return (
    <Drawer
      title={
        <Space>
          <UserOutlined />
          <span>玩家详情</span>
          {player && (
            <Tag color={player.is_online ? 'success' : 'default'}>
              {player.is_online ? '在线' : '离线'}
            </Tag>
          )}
        </Space>
      }
      placement="right"
      size={800}
      open={open}
      onClose={onClose}
      destroyOnHidden
    >
      {playerLoading ? (
        <LoadingSpinner height="16rem" />
      ) : !player ? (
        <Empty description="未找到玩家信息" />
      ) : (
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'overview',
              label: (
                <span>
                  <UserOutlined />
                  概览
                </span>
              ),
              children: (
                <Space orientation="vertical" size="large" className="w-full">
                  {/* 玩家基本信息卡片 */}
                  <Card title="基本信息">
                    <div className="flex items-start space-x-6 mb-6">
                      {/* 头像和皮肤 */}
                      <div className="flex flex-col items-center space-y-2">
                        <MCAvatar
                          avatarBase64={player.avatar_base64}
                          size={80}
                          playerName={player.current_name}
                        />
                        {player.skin_base64 && (
                          <div className="text-center">
                            <Image
                              width={64}
                              src={`data:image/png;base64,${player.skin_base64}`}
                              alt="Player Skin"
                              preview={{
                                mask: '查看皮肤',
                                imageRender: () => (
                                  <img
                                    src={`data:image/png;base64,${player.skin_base64}`}
                                    alt="Player Skin"
                                    style={{
                                      imageRendering: 'pixelated',
                                      width: '256px',
                                      height: 'auto'
                                    }}
                                  />
                                )
                              }}
                            />
                          </div>
                        )}
                        <Button
                          size="small"
                          icon={<ReloadOutlined />}
                          loading={refreshingSkin}
                          onClick={handleRefreshSkin}
                        >
                          刷新皮肤
                        </Button>
                      </div>

                      {/* 详细信息 */}
                      <div className="flex-1">
                        <Descriptions column={1} size="small">
                          <Descriptions.Item label="玩家名称">
                            <Text strong className="text-lg">{player.current_name}</Text>
                          </Descriptions.Item>
                          <Descriptions.Item label="UUID">
                            <Text copyable code>{formatUUID(player.uuid)}</Text>
                          </Descriptions.Item>
                          <Descriptions.Item label="当前在线">
                            {player.current_servers.length > 0 ? (
                              <Space wrap>
                                {player.current_servers.map(serverId => (
                                  <Tag key={serverId} color="success" icon={<GlobalOutlined />}>
                                    {serverId}
                                  </Tag>
                                ))}
                              </Space>
                            ) : (
                              <Text type="secondary">当前离线</Text>
                            )}
                          </Descriptions.Item>
                          <Descriptions.Item label="首次加入">
                            {new Date(player.first_seen).toLocaleString('zh-CN')}
                          </Descriptions.Item>
                          <Descriptions.Item label="最后在线">
                            {player.last_seen
                              ? new Date(player.last_seen).toLocaleString('zh-CN')
                              : '从未离线'}
                          </Descriptions.Item>
                        </Descriptions>
                      </div>
                    </div>
                  </Card>

                  {/* 统计数据 */}
                  <Card title="统计数据">
                    <Row gutter={16}>
                      <Col span={12}>
                        <Statistic
                          title="总游戏时长"
                          value={formatDuration(player.total_playtime_seconds)}
                          prefix={<ClockCircleOutlined />}
                        />
                      </Col>
                      <Col span={12}>
                        <Statistic
                          title="总会话数"
                          value={player.total_sessions}
                          prefix={<CalendarOutlined />}
                        />
                      </Col>
                      <Col span={12} className="mt-4">
                        <Statistic
                          title="聊天消息数"
                          value={player.total_messages}
                          prefix={<MessageOutlined />}
                        />
                      </Col>
                      <Col span={12} className="mt-4">
                        <Statistic
                          title="获得成就数"
                          value={player.total_achievements}
                          prefix={<TrophyOutlined />}
                        />
                      </Col>
                    </Row>
                  </Card>

                  {/* 会话统计 */}
                  {sessionStats && (
                    <Card title="会话统计">
                      <Row gutter={16}>
                        <Col span={12}>
                          <Statistic
                            title="平均会话时长"
                            value={formatDuration(sessionStats.average_session_seconds)}
                          />
                        </Col>
                        <Col span={12}>
                          <Statistic
                            title="最长会话时长"
                            value={formatDuration(sessionStats.longest_session_seconds)}
                          />
                        </Col>
                      </Row>

                      {Object.keys(sessionStats.playtime_by_server).length > 0 && (
                        <div className="mt-4">
                          <Text strong>各服务器游戏时长</Text>
                          <div className="mt-2 space-y-2">
                            {Object.entries(sessionStats.playtime_by_server).map(([serverId, seconds]) => (
                              <div key={serverId} className="flex justify-between items-center">
                                <Tag color="blue">{serverId}</Tag>
                                <Text>{formatDuration(seconds)}</Text>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </Card>
                  )}
                </Space>
              )
            },
            {
              key: 'sessions',
              label: (
                <span>
                  <CalendarOutlined />
                  游戏会话 ({sessions.length})
                </span>
              ),
              children: (
                <Table
                  dataSource={sessions}
                  columns={sessionColumns}
                  rowKey="session_id"
                  size="small"
                  loading={sessionsLoading}
                  pagination={{
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条会话`
                  }}
                  locale={{
                    emptyText: <Empty description="暂无会话记录" />
                  }}
                />
              )
            },
            {
              key: 'chat',
              label: (
                <span>
                  <MessageOutlined />
                  聊天记录 ({chatMessages.length})
                </span>
              ),
              children: (
                <Table
                  dataSource={chatMessages}
                  columns={chatColumns}
                  rowKey="message_id"
                  size="small"
                  loading={chatLoading}
                  pagination={{
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条消息`
                  }}
                  locale={{
                    emptyText: <Empty description="暂无聊天记录" />
                  }}
                />
              )
            },
            {
              key: 'achievements',
              label: (
                <span>
                  <TrophyOutlined />
                  成就 ({achievements.length})
                </span>
              ),
              children: (
                <Table
                  dataSource={achievements}
                  columns={achievementColumns}
                  rowKey="achievement_id"
                  size="small"
                  loading={achievementsLoading}
                  pagination={{
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 个成就`
                  }}
                  locale={{
                    emptyText: <Empty description="暂无成就记录" />
                  }}
                />
              )
            }
          ]}
        />
      )}
    </Drawer>
  );
};

export default PlayerDetailDrawer;
