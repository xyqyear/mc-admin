import React from 'react'
import { Card, Row, Col, Alert, Button, Space } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
import {
  DashboardOutlined,
} from '@ant-design/icons'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import ServerOperationButtons from '@/components/server/ServerOperationButtons'
import ServerAddressCard from '@/components/server/ServerAddressCard'
import ServerInfoCard from '@/components/server/ServerInfoCard'
import ServerStatsCard from '@/components/server/ServerStatsCard'
import ServerDiskUsageCard from '@/components/server/ServerDiskUsageCard'
import ServerResourcesCard from '@/components/server/ServerResourcesCard'
import ServerIOStatsCard from '@/components/server/ServerIOStatsCard'
import OnlinePlayersCard from '@/components/server/OnlinePlayersCard'
import ServerRestartScheduleCard from '@/components/server/ServerRestartScheduleCard'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'

const ServerDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // 获取所有服务器列表用于错误提示
  const { useServers } = useServerQueries()
  const allServersQuery = useServers()

  // 使用新的数据管理系统
  const { useServerDetailData } = useServerDetailQueries(id || '')

  // 获取服务器详情数据
  const {
    serverInfo,
    status,
    cpu,
    memory,
    players,
    iostats,
    diskUsage,
    restartSchedule,
    restartScheduleQuery,
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
                  <p>服务器 &quot;{id}&quot; 不存在。</p>
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

  return (
    <div className="space-y-4">
      <PageHeader
        title="概览"
        icon={<DashboardOutlined />}
        serverTag={serverInfo.name}
        actions={
          <ServerOperationButtons
            serverId={id}
            serverName={serverInfo.name}
            status={status}
          />
        }
      />


      {/* 服务器状态统计 */}
      <ServerStatsCard
        serverInfo={serverInfo}
        playersCount={players?.length || 0}
        isRunning={isRunning || false}
      />

      {/* 服务器地址和详情 */}
      <Row gutter={16}>
        <Col xs={24} sm={24} md={24} lg={12} xl={12}>
          <ServerAddressCard serverId={id} />
        </Col>
        <Col xs={24} sm={24} md={24} lg={12} xl={12}>
          <ServerInfoCard serverInfo={serverInfo} />
        </Col>
      </Row>

      {/* 重启计划和磁盘使用空间 */}
      <Row gutter={16}>
        <Col xs={24} sm={24} md={24} lg={8} xl={6}>
          <ServerRestartScheduleCard
            restartSchedule={restartSchedule}
            isLoading={restartScheduleQuery?.isLoading}
          />
        </Col>
        <Col xs={24} sm={24} md={24} lg={16} xl={18}>
          <ServerDiskUsageCard
            diskUsageBytes={diskUsage?.diskUsageBytes}
            diskTotalBytes={diskUsage?.diskTotalBytes}
            diskAvailableBytes={diskUsage?.diskAvailableBytes}
            hasDiskUsageData={hasDiskUsageData || false}
          />
        </Col>
      </Row>

      {/* 系统资源使用情况 - 仅在运行状态显示CPU和内存 */}
      <ServerResourcesCard
        cpuPercentage={cpu?.cpuPercentage}
        memoryUsageBytes={memory?.memoryUsageBytes}
        serverInfo={serverInfo}
        isRunning={isRunning || false}
        hasCpuData={hasCpuData || false}
        hasMemoryData={hasMemoryData || false}
      />

      {/* I/O统计 - 仅在运行状态且有I/O数据时显示 */}
      <ServerIOStatsCard
        diskReadBytes={iostats?.diskReadBytes}
        diskWriteBytes={iostats?.diskWriteBytes}
        networkReceiveBytes={iostats?.networkReceiveBytes}
        networkSendBytes={iostats?.networkSendBytes}
        isRunning={isRunning || false}
        hasIOStatsData={hasIOStatsData || false}
      />

      {/* 在线玩家列表 - 使用新的增强组件 */}
      <OnlinePlayersCard
        serverId={id}
        isHealthy={isHealthy || false}
      />

    </div>
  )
}

export default ServerDetail
