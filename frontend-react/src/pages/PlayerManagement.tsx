import React, { useState, useMemo } from 'react';
import {
  Card,
  Table,
  Button,
  Alert,
  Tag,
  Typography,
  Space,
  Empty,
  Tooltip
} from 'antd';
import {
  ReloadOutlined,
  TeamOutlined,
  ClockCircleOutlined,
  CalendarOutlined
} from '@ant-design/icons';
import type { TableProps } from 'antd';
import PageHeader from '@/components/layout/PageHeader';
import PlayerFilters from '@/components/players/PlayerFilters';
import PlayerDetailDrawer from '@/components/players/PlayerDetailDrawer';
import { MCAvatar } from '@/components/players/MCAvatar';
import { useAllPlayers } from '@/hooks/queries/base/usePlayerQueries';
import { useServerQueries } from '@/hooks/queries/base/useServerQueries';
import type { PlayerSummary } from '@/hooks/api/playerApi';
import { formatUUID } from '@/utils/formatUtils';

const { Text } = Typography;

const PlayerManagement: React.FC = () => {
  const [selectedPlayerUUID, setSelectedPlayerUUID] = useState<string | null>(null);
  const [filters, setFilters] = useState<{
    online_only?: boolean;
    server_id?: string;
    search?: string;
  }>({});

  // 获取服务器列表用于筛选
  const { useServers } = useServerQueries();
  const { data: servers = [] } = useServers();

  // 获取玩家列表
  const {
    data: allPlayers = [],
    isLoading,
    error,
    refetch
  } = useAllPlayers({
    online_only: filters.online_only,
    server_id: filters.server_id
  });

  // 客户端搜索过滤
  const filteredPlayers = useMemo(() => {
    if (!filters.search) return allPlayers;
    const searchLower = filters.search.toLowerCase();
    return allPlayers.filter(
      player =>
        player.current_name.toLowerCase().includes(searchLower) ||
        player.uuid.toLowerCase().includes(searchLower)
    );
  }, [allPlayers, filters.search]);

  // 服务器选项
  const serverOptions = useMemo(
    () =>
      servers.map(server => ({
        label: server.name,
        value: server.id
      })),
    [servers]
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

  const handleFiltersChange = (newFilters: typeof filters) => {
    setFilters(newFilters);
  };

  const handleFiltersReset = () => {
    setFilters({});
  };

  const handleViewPlayer = (uuid: string) => {
    setSelectedPlayerUUID(uuid);
  };

  const handleCloseDrawer = () => {
    setSelectedPlayerUUID(null);
  };

  // 表格列定义
  const columns: TableProps<PlayerSummary>['columns'] = [
    {
      title: '玩家',
      key: 'player',
      width: 250,
      render: (_, record) => (
        <div className="flex items-center space-x-3">
          <MCAvatar
            avatarBase64={record.avatar_base64}
            size={40}
            playerName={record.current_name}
          />
          <div className="flex-1 min-w-0">
            <div className="font-medium text-base truncate" title={record.current_name}>
              {record.current_name}
            </div>
            <div className="text-xs text-gray-500 truncate" title={formatUUID(record.uuid)}>
              UUID: {formatUUID(record.uuid)}
            </div>
          </div>
        </div>
      )
    },
    {
      title: '状态',
      dataIndex: 'is_online',
      key: 'status',
      width: 100,
      render: (isOnline: boolean) => (
        <Tag color={isOnline ? 'success' : 'default'}>
          {isOnline ? '在线' : '离线'}
        </Tag>
      ),
      filters: [
        { text: '在线', value: true },
        { text: '离线', value: false }
      ],
      onFilter: (value, record) => record.is_online === value
    },
    {
      title: '总游戏时长',
      dataIndex: 'total_playtime_seconds',
      key: 'playtime',
      width: 150,
      render: (seconds: number) => (
        <Tooltip title={`${seconds}秒`}>
          <Space>
            <ClockCircleOutlined />
            <Text>{formatDuration(seconds)}</Text>
          </Space>
        </Tooltip>
      ),
      sorter: (a, b) => a.total_playtime_seconds - b.total_playtime_seconds
    },
    {
      title: '首次加入',
      dataIndex: 'first_seen',
      key: 'first_seen',
      width: 180,
      render: (date: string) => (
        <Space>
          <CalendarOutlined />
          <Text>{new Date(date).toLocaleString('zh-CN')}</Text>
        </Space>
      ),
      sorter: (a, b) => new Date(a.first_seen).getTime() - new Date(b.first_seen).getTime()
    },
    {
      title: '最后在线',
      dataIndex: 'last_seen',
      key: 'last_seen',
      width: 180,
      defaultSortOrder: 'descend', // 默认降序排列（最近见到的在前）
      render: (date: string | null) => (
        <Space>
          <CalendarOutlined />
          <Text>{date ? new Date(date).toLocaleString('zh-CN') : '从未上线'}</Text>
        </Space>
      ),
      sorter: (a, b) => {
        const aTime = a.last_seen ? new Date(a.last_seen).getTime() : 0;
        const bTime = b.last_seen ? new Date(b.last_seen).getTime() : 0;
        return aTime - bTime;
      }
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          onClick={() => handleViewPlayer(record.uuid)}
        >
          查看详情
        </Button>
      )
    }
  ];

  return (
    <div className="h-full w-full flex flex-col space-y-4">
      <PageHeader
        title="玩家管理"
        icon={<TeamOutlined />}
        actions={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            loading={isLoading}
          >
            刷新
          </Button>
        }
      />

      {/* 错误提示 */}
      {error && (
        <Alert
          title="加载玩家数据失败"
          description={error.message || '发生未知错误'}
          type="error"
          showIcon
          closable
          action={
            <Button size="small" danger onClick={() => refetch()}>
              重试
            </Button>
          }
        />
      )}

      {/* 玩家列表 */}
      <Card
        title={
          <div className="flex items-center space-x-2">
            <TeamOutlined />
            <span>玩家列表</span>
            <Text type="secondary" className="text-sm font-normal">
              ({filteredPlayers.length} 个玩家)
            </Text>
          </div>
        }
      >
        {/* 筛选器 */}
        <PlayerFilters
          serverOptions={serverOptions}
          filters={filters}
          onChange={handleFiltersChange}
          onReset={handleFiltersReset}
          loading={isLoading}
        />

        {/* 玩家表格 */}
        <Table
          dataSource={filteredPlayers}
          columns={columns}
          rowKey="player_db_id"
          size="middle"
          scroll={{ x: 'max-content' }}
          loading={isLoading}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total, range) => `${range[0]}-${range[1]} 共 ${total} 个玩家`
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <div className="space-y-2">
                    <div>暂无玩家数据</div>
                    <div className="text-sm text-gray-400">
                      玩家数据会在玩家首次加入服务器时自动记录
                    </div>
                  </div>
                }
              />
            )
          }}
        />
      </Card>

      {/* 玩家详情抽屉 */}
      <PlayerDetailDrawer
        uuid={selectedPlayerUUID}
        open={!!selectedPlayerUUID}
        onClose={handleCloseDrawer}
      />
    </div>
  );
};

export default PlayerManagement;
