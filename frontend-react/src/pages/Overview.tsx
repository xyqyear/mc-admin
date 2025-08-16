import React from 'react'
import { Card, Table, Button, Tooltip, Space } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  DownOutlined,
  ExportOutlined,
} from '@ant-design/icons'
import MetricCard from '@/components/overview/MetricCard'
import ServerStateTag from '@/components/overview/ServerStateTag'
import type { ServerInfo, SystemInfo } from '@/types/Server'

// Mock data - in a real app this would come from API
const mockSystemInfo: SystemInfo = {
  cpuPercentage: 10,
  cpuLoad1Min: 1.0,
  cpuLoad5Min: 1.0,
  cpuLoad15Min: 1.0,
  ramUsedGB: 20.0,
  ramTotalGB: 48.0,
  diskUsedGB: 40.0,
  diskTotalGB: 400.0,
  backupUsedGB: 80.0,
  backupTotalGB: 256.0,
}

const mockServersInfo: ServerInfo[] = [
  {
    id: 'vanilla',
    onlinePlayers: ['player1', 'player2'],
    state: 'running',
    diskUsedGB: 20,
    port: 25565,
  },
  {
    id: 'creative',
    onlinePlayers: [],
    state: 'paused',
    diskUsedGB: 30,
    port: 25566,
  },
  {
    id: 'fc4',
    onlinePlayers: [],
    state: 'stopped',
    diskUsedGB: 40,
    port: 25567,
  },
  {
    id: 'monifactory',
    onlinePlayers: [],
    state: 'down',
    diskUsedGB: 50,
    port: 25568,
  },
]

const Overview: React.FC = () => {
  const navigate = useNavigate()
  
  const serverNum = mockServersInfo.length
  const onlinePlayerNum = mockServersInfo.reduce(
    (acc, server) => acc + server.onlinePlayers.length,
    0
  )

  const isOperationAvailable = (operation: string, server: ServerInfo) => {
    switch (operation) {
      case 'start':
        return ['stopped', 'paused', 'down'].includes(server.state)
      case 'pause':
        return server.state === 'running'
      case 'stop':
        return ['running', 'paused'].includes(server.state)
      case 'restart':
        return ['running', 'paused'].includes(server.state)
      case 'down':
        return ['running', 'stopped', 'paused'].includes(server.state)
      default:
        return false
    }
  }

  const handleServerOperation = (operation: string, serverId: string) => {
    console.log(`${operation} server ${serverId}`)
    // TODO: Implement server operations
  }

  const columns = [
    {
      title: '服务器',
      dataIndex: 'id',
      key: 'id',
      width: 120,
    },
    {
      title: '端口',
      dataIndex: 'port',
      key: 'port',
      width: 70,
    },
    {
      title: '状态',
      dataIndex: 'state',
      key: 'state',
      width: 100,
      render: (state: ServerInfo['state']) => <ServerStateTag state={state} />,
    },
    {
      title: '硬盘使用',
      dataIndex: 'diskUsedGB',
      key: 'diskUsedGB',
      width: 100,
      render: (diskUsedGB: number) => `${diskUsedGB.toFixed(1)}GB`,
    },
    {
      title: '玩家数量',
      dataIndex: 'onlinePlayers',
      key: 'playerCount',
      width: 100,
      render: (onlinePlayers: string[]) => onlinePlayers.length,
    },
    {
      title: '在线玩家',
      dataIndex: 'onlinePlayers',
      key: 'onlinePlayers',
      render: (onlinePlayers: string[]) => onlinePlayers.join(', ') || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      fixed: 'right' as const,
      render: (_: any, record: ServerInfo) => (
        <Space>
          <Tooltip title="启动">
            <Button
              icon={<PlayCircleOutlined />}
              size="small"
              disabled={!isOperationAvailable('start', record)}
              onClick={() => handleServerOperation('start', record.id)}
            />
          </Tooltip>
          <Tooltip title="暂停">
            <Button
              icon={<PauseCircleOutlined />}
              size="small"
              disabled={!isOperationAvailable('pause', record)}
              onClick={() => handleServerOperation('pause', record.id)}
            />
          </Tooltip>
          <Tooltip title="停止">
            <Button
              icon={<StopOutlined />}
              size="small"
              disabled={!isOperationAvailable('stop', record)}
              onClick={() => handleServerOperation('stop', record.id)}
            />
          </Tooltip>
          <Tooltip title="重启">
            <Button
              icon={<ReloadOutlined />}
              size="small"
              disabled={!isOperationAvailable('restart', record)}
              onClick={() => handleServerOperation('restart', record.id)}
            />
          </Tooltip>
          <Tooltip title="离线">
            <Button
              icon={<DownOutlined />}
              size="small"
              disabled={!isOperationAvailable('down', record)}
              onClick={() => handleServerOperation('down', record.id)}
            />
          </Tooltip>
          <Tooltip title="详情">
            <Button
              icon={<ExportOutlined />}
              size="small"
              type="primary"
              onClick={() => navigate(`/server/${record.id}`)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div className="h-full w-full flex flex-col">
      <div className="flex flex-wrap gap-4 mb-4">
        <MetricCard value={serverNum} title="服务器总数" />
        <MetricCard value={onlinePlayerNum} title="在线玩家总数" />
        <MetricCard
          value={mockSystemInfo.cpuPercentage}
          title="CPU占用"
          extraValues={`${mockSystemInfo.cpuLoad1Min.toFixed(2)}, ${mockSystemInfo.cpuLoad5Min.toFixed(2)}, ${mockSystemInfo.cpuLoad15Min.toFixed(2)}`}
          isProgress
        />
        <MetricCard
          value={(mockSystemInfo.ramUsedGB / mockSystemInfo.ramTotalGB) * 100}
          title="RAM占用"
          extraValues={`${mockSystemInfo.ramUsedGB}GB / ${mockSystemInfo.ramTotalGB}GB`}
          isProgress
        />
        <MetricCard
          value={(mockSystemInfo.diskUsedGB / mockSystemInfo.diskTotalGB) * 100}
          title="硬盘使用"
          extraValues={`${mockSystemInfo.diskUsedGB}GB / ${mockSystemInfo.diskTotalGB}GB`}
          isProgress
        />
        <MetricCard
          value={(mockSystemInfo.backupUsedGB / mockSystemInfo.backupTotalGB) * 100}
          title="备份空间"
          extraValues={`${mockSystemInfo.backupUsedGB}GB / ${mockSystemInfo.backupTotalGB}GB`}
          isProgress
        />
      </div>
      
      <div className="flex-1">
        <Card>
          <Table
            dataSource={mockServersInfo}
            columns={columns}
            rowKey="id"
            scroll={{ x: 1000 }}
            pagination={false}
          />
        </Card>
      </div>
    </div>
  )
}

export default Overview
