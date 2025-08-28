import React from 'react'
import { Typography, Button, Space, Table, Tag, Alert, Progress, Card } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
import { UserOutlined } from '@ant-design/icons'
import type { Player } from '@/types/Server'
import { useServerDetailQueries } from '@/hooks/queries/useServerDetailQueries'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'

const { Title } = Typography

const ServerPlayers: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  
  // 使用新的数据管理系统
  const { useServerDetailData } = useServerDetailQueries(id || '')
  const { useRconCommand } = useServerMutations()
  
  // 获取服务器详情数据
  const {
    serverInfo,
    players,
    isLoading,
    isError,
    error,
    hasServerInfo,
    isHealthy,
  } = useServerDetailData()
  
  // RCON 命令执行
  const rconCommandMutation = useRconCommand(id || '')

  // 将玩家字符串数组转换为完整的 Player 对象
  const playersData: Player[] = (players || []).map((playerName) => ({
    username: playerName,
    uuid: `mock-uuid-${playerName}`, // 在实际实现中，这应该从API获取
    isOnline: true, // 从在线玩家列表来的都是在线的
    playtimeHours: Math.floor(Math.random() * 200), // Mock 数据
    firstJoined: '2024-01-01', // Mock 数据
    lastSeen: new Date().toISOString(), // Mock 数据
  }))

  // 如果没有服务器ID，返回错误
  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="参数错误"
          description="缺少服务器ID参数"
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // 错误状态
  if (isError || !hasServerInfo) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="加载失败"
          description={error?.message || `无法加载服务器 "${id}" 的信息`}
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // 加载状态
  if (isLoading || !serverInfo) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <div className="text-center">
          <div className="mb-4">加载玩家数据中...</div>
          <Progress percent={30} status="active" showInfo={false} />
        </div>
      </div>
    )
  }

  // 玩家操作处理
  const handlePlayerOperation = (action: string, playerName: string) => {
    let command = ''
    switch (action) {
      case 'kick':
        command = `kick ${playerName}`
        break
      case 'ban':
        command = `ban ${playerName}`
        break
      case 'op':
        command = `op ${playerName}`
        break
      case 'deop':
        command = `deop ${playerName}`
        break
      default:
        return
    }
    
    rconCommandMutation.mutate(command)
  }

  const playerColumns = [
    {
      title: 'Player',
      dataIndex: 'username',
      key: 'username',
      render: (username: string, player: Player) => (
        <div className="flex items-center gap-2">
          <UserOutlined />
          <span className="font-medium">{username}</span>
          {player.isOnline && <Tag color="green">Online</Tag>}
          {!player.isOnline && <Tag color="default">Offline</Tag>}
        </div>
      )
    },
    {
      title: 'Playtime',
      dataIndex: 'playtimeHours',
      key: 'playtime',
      render: (hours: number) => `${hours}h`,
      sorter: (a: Player, b: Player) => (a.playtimeHours || 0) - (b.playtimeHours || 0)
    },
    {
      title: 'First Joined',
      dataIndex: 'firstJoined',
      key: 'firstJoined',
      render: (date: string) => new Date(date).toLocaleDateString()
    },
    {
      title: 'Last Seen',
      dataIndex: 'lastSeen',
      key: 'lastSeen',
      render: (date: string) => new Date(date).toLocaleString()
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, player: Player) => (
        <Space>
          <Button 
            size="small" 
            type="link"
            disabled={!isHealthy}
            loading={rconCommandMutation.isPending}
            onClick={() => handlePlayerOperation('kick', player.username)}
          >
            Kick
          </Button>
          <Button 
            size="small" 
            type="link"
            disabled={!isHealthy}
            loading={rconCommandMutation.isPending}
            onClick={() => handlePlayerOperation('ban', player.username)}
          >
            Ban
          </Button>
          <Button 
            size="small" 
            type="link"
            disabled={!isHealthy}
            loading={rconCommandMutation.isPending}
            onClick={() => handlePlayerOperation('op', player.username)}
          >
            OP
          </Button>
        </Space>
      )
    }
  ]

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <Title level={2} className="!mb-0 !mt-0">{serverInfo.name} - 玩家列表</Title>
        <Space>
          <Button 
            type="primary"
            icon={<UserOutlined />}
            disabled={!isHealthy}
            onClick={() => {
              // TODO: 实现添加玩家功能 (通过 RCON 命令)
              console.log('Add player functionality')
            }}
          >
            添加玩家
          </Button>
        </Space>
      </div>

      <Card>
        <div className="mb-4">
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span>在线玩家: {playersData.length}</span>
            <span>服务器状态: {isHealthy ? '健康' : '未运行'}</span>
            {!isHealthy && (
              <span className="text-orange-600">注意: 服务器未运行时无法执行玩家操作</span>
            )}
          </div>
        </div>
        
        <Table
          dataSource={playersData}
          columns={playerColumns}
          rowKey="uuid"
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} players`
          }}
          locale={{
            emptyText: isHealthy 
              ? '当前没有在线玩家' 
              : '服务器未运行，无法获取玩家信息'
          }}
        />
      </Card>
    </div>
  )
}

export default ServerPlayers
