import React from 'react'
import { Card, Row, Col, Statistic, Button, Space, Progress, Alert, Descriptions, Typography, Tooltip } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
import {
  PlayCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  UserOutlined,
  HddOutlined,
  WifiOutlined,
  GlobalOutlined,
} from '@ant-design/icons'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import { useServerDetailQueries } from '@/hooks/queries/useServerDetailQueries'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { serverStatusUtils } from '@/utils/serverUtils'
import { useServerQueries } from '@/hooks/queries/useServerQueries'

const { Title } = Typography

const ServerDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // 获取所有服务器列表用于错误提示
  const { useServers } = useServerQueries()
  const allServersQuery = useServers()

  // 使用新的数据管理系统
  const { useServerDetailData } = useServerDetailQueries(id || '')
  const { useServerOperation } = useServerMutations()

  // 获取服务器详情数据
  const {
    serverInfo,
    status,
    cpu,
    memory,
    players,
    iostats,
    diskUsage,
    isLoading,
    isError,
    error,
    hasServerInfo,
    hasCpuData,
    hasMemoryData,
    hasIOStatsData,
    hasDiskUsageData,
    isRunning,
    isHealthy,
  } = useServerDetailData()

  // 服务器操作
  const serverOperationMutation = useServerOperation()

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
              返回总览
            </Button>
          }
        />
      </div>
    )
  }

  // 错误状态
  if (isError) {
    const isServerNotFound = error?.message.includes('not found')
    const availableServers = allServersQuery.data || []

    return (
      <div className="flex justify-center items-center min-h-64">
        <Card className="max-w-md">
          <Alert
            message={isServerNotFound ? "服务器未找到" : "加载失败"}
            description={
              isServerNotFound ? (
                <div className="space-y-3">
                  <p>服务器 "{id}" 不存在。</p>
                  {availableServers.length > 0 && (
                    <div>
                      <p className="font-medium">可用的服务器：</p>
                      <div className="space-y-1">
                        {availableServers.map(server => (
                          <Button
                            key={server.id}
                            type="link"
                            size="small"
                            className="block text-left p-0 h-auto"
                            onClick={() => navigate(`/server/${server.id}`)}
                          >
                            {server.name} ({server.id})
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                error?.message || `无法加载服务器 "${id}" 的信息`
              )
            }
            type="error"
            action={
              <Space direction="vertical">
                <Button size="small" onClick={() => navigate('/overview')}>
                  返回总览
                </Button>
                {isServerNotFound && availableServers.length > 0 && (
                  <Button size="small" type="primary" onClick={() => navigate(`/server/${availableServers[0].id}`)}>
                    访问 {availableServers[0].name}
                  </Button>
                )}
              </Space>
            }
          />
        </Card>
      </div>
    )
  }

  // 加载状态
  if (isLoading || !hasServerInfo || !serverInfo) {
    return <LoadingSpinner height="16rem" />
  }

  // 服务器操作处理
  const handleServerOperation = (action: string) => {
    serverOperationMutation.mutate({ action, serverId: id })
  }

  // 检查操作是否可用
  const isOperationAvailable = (operation: string) => {
    if (!status) return false
    return serverStatusUtils.isOperationAvailable(operation, status)
  }

  return (
    <div className="space-y-4">
      {/* 页面头部 */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <Title level={2} className="!mb-0 !mt-0">{serverInfo.name}</Title>
        </div>
        <Space>
          <Tooltip title="启动服务器">
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!isOperationAvailable('start')}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('start')}
            >
              启动
            </Button>
          </Tooltip>
          <Tooltip title="停止服务器">
            <Button
              icon={<StopOutlined />}
              disabled={!isOperationAvailable('stop')}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('stop')}
            >
              停止
            </Button>
          </Tooltip>
          <Tooltip title="重启服务器">
            <Button
              icon={<ReloadOutlined />}
              disabled={!isOperationAvailable('restart')}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('restart')}
            >
              重启
            </Button>
          </Tooltip>
          <Button onClick={() => navigate('/overview')}>返回总览</Button>
        </Space>
      </div>


      {/* 服务器状态统计 */}
      <Card>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="在线玩家"
              value={players?.length || 0}
              suffix={`/ ${20}`} // 默认最大玩家数，后续可从配置获取
              prefix={<UserOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="游戏端口"
              value={serverInfo.gamePort}
              formatter={(value) => `${value}`}
              prefix={<GlobalOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="RCON端口"
              value={serverInfo.rconPort}
              formatter={(value) => `${value}`}
              prefix={<HddOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="运行时间"
              value={isRunning ? '运行中' : '未运行'}
              prefix={<WifiOutlined />}
            />
          </Col>
        </Row>
      </Card>

      {/* 磁盘使用空间 - 始终显示 */}
      <Card title="磁盘使用空间">
        {hasDiskUsageData && diskUsage ? (
          <div>
            <div className="flex justify-between mb-2">
              <span className="text-base font-medium">存储空间分配</span>
              <span className="text-sm text-gray-600">
                服务器: {(diskUsage.diskUsageBytes / (1024 ** 3)).toFixed(1)}GB /
                剩余: {(diskUsage.diskAvailableBytes / (1024 ** 3)).toFixed(1)}GB /
                总计: {(diskUsage.diskTotalBytes / (1024 ** 3)).toFixed(1)}GB
              </span>
            </div>
            <Progress
              percent={((diskUsage.diskTotalBytes - diskUsage.diskAvailableBytes) / diskUsage.diskTotalBytes) * 100}
              success={{
                percent: (diskUsage.diskUsageBytes / diskUsage.diskTotalBytes) * 100,
                strokeColor: '#52c41a'
              }}
              strokeColor="#faad14"
              showInfo={false}
              size="default"
            />
            <div className="mt-2 text-xs text-gray-500">
              <span className="inline-block w-3 h-3 bg-green-500 rounded mr-1"></span>该服务器使用
              <span className="inline-block w-3 h-3 bg-yellow-500 rounded mx-1 ml-4"></span>其他文件使用
              <span className="ml-4">未填充部分为剩余空间</span>
            </div>
          </div>
        ) : (
          <div className="text-center text-gray-500 py-8">
            <p>磁盘使用信息暂不可用</p>
            <p className="text-xs">请检查服务器连接状态</p>
          </div>
        )}
      </Card>

      {/* 系统资源使用情况 - 仅在运行状态显示CPU和内存 */}
      {isRunning && (hasCpuData || hasMemoryData) && (cpu || memory) && (
        <Card title="系统资源使用情况">
          <Row gutter={[16, 16]}>
            {hasCpuData && cpu && (
              <Col span={12}>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>CPU 使用率</span>
                    <span>{cpu.cpuPercentage.toFixed(1)}%</span>
                  </div>
                  <Progress
                    percent={cpu.cpuPercentage}
                    strokeColor={cpu.cpuPercentage > 80 ? '#ff4d4f' : cpu.cpuPercentage > 60 ? '#faad14' : '#52c41a'}
                    showInfo={false}
                  />
                </div>
              </Col>
            )}
            {hasMemoryData && memory && (
              <Col span={12}>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>内存使用</span>
                    <span>
                      {(memory.memoryUsageBytes / (1024 ** 3)).toFixed(1)}GB /
                      {(serverInfo.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB
                    </span>
                  </div>
                  <Progress
                    percent={(memory.memoryUsageBytes / serverInfo.maxMemoryBytes) * 100}
                    strokeColor={(memory.memoryUsageBytes / serverInfo.maxMemoryBytes) > 0.8 ? '#ff4d4f' :
                      (memory.memoryUsageBytes / serverInfo.maxMemoryBytes) > 0.6 ? '#faad14' : '#52c41a'}
                    showInfo={false}
                  />
                </div>
              </Col>
            )}
          </Row>
        </Card>
      )}

      {/* I/O统计 - 仅在运行状态且有I/O数据时显示 */}
      {isRunning && hasIOStatsData && iostats && (
        <Card title="I/O统计">
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between mb-1">
                    <span>磁盘读取</span>
                    <span>{(iostats.diskReadBytes / (1024 ** 2)).toFixed(1)}MB</span>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>磁盘写入</span>
                    <span>{(iostats.diskWriteBytes / (1024 ** 2)).toFixed(1)}MB</span>
                  </div>
                </div>
              </div>
            </Col>
            <Col span={12}>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between mb-1">
                    <span>网络接收</span>
                    <span>{(iostats.networkReceiveBytes / (1024 ** 2)).toFixed(1)}MB</span>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>网络发送</span>
                    <span>{(iostats.networkSendBytes / (1024 ** 2)).toFixed(1)}MB</span>
                  </div>
                </div>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* 在线玩家列表 */}
      {isHealthy && players && players.length > 0 && (
        <Card title={`在线玩家 (${players.length})`}>
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
      )}

      {/* 服务器详细信息 */}
      <Card title="服务器详情">
        <Descriptions column={2}>
          <Descriptions.Item label="服务器ID">{serverInfo.id}</Descriptions.Item>
          <Descriptions.Item label="服务器类型">{serverInfo.serverType}</Descriptions.Item>
          <Descriptions.Item label="游戏版本">{serverInfo.gameVersion}</Descriptions.Item>
          <Descriptions.Item label="Java版本">{serverInfo.javaVersion}</Descriptions.Item>
          <Descriptions.Item label="游戏端口">{serverInfo.gamePort}</Descriptions.Item>
          <Descriptions.Item label="RCON端口">{serverInfo.rconPort}</Descriptions.Item>
          <Descriptions.Item label="最大内存">
            {(serverInfo.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB
          </Descriptions.Item>
          <Descriptions.Item label="服务器路径">{serverInfo.path}</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  )
}

export default ServerDetail
