import React from 'react'
import { useParams, useNavigate } from 'react-router'
import { LayoutDashboard } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import ServerOperationButtons from '@/components/server/ServerOperationButtons'
import ServerAddressCard from '@/components/server/ServerAddressCard'
import ServerInfoCard from '@/components/server/ServerInfoCard'
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

  const { useServers } = useServerQueries()
  const allServersQuery = useServers()

  const { useServerDetailData } = useServerDetailQueries(id || '')

  const {
    serverInfo,
    status,
    cpu,
    memory,
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

  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert variant="destructive">
          <AlertTitle>参数错误</AlertTitle>
          <AlertDescription>
            <div className="flex items-center justify-between">
              <span>缺少服务器ID参数</span>
              <Button size="sm" variant="outline" onClick={() => navigate('/overview')}>
                返回总览
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (isError) {
    const isServerNotFound = error?.message.includes('not found')
    const availableServers = allServersQuery.data || []

    return (
      <div className="flex justify-center items-center min-h-64">
        <Card className="max-w-md">
          <CardContent className="pt-6">
            <Alert variant="destructive">
              <AlertTitle>{isServerNotFound ? "服务器未找到" : "加载失败"}</AlertTitle>
              <AlertDescription>
                {isServerNotFound ? (
                  <div className="space-y-3">
                    <p>服务器 &quot;{id}&quot; 不存在。</p>
                    {availableServers.length > 0 && (
                      <div>
                        <p className="font-medium">可用的服务器：</p>
                        <div className="space-y-1">
                          {availableServers.map(server => (
                            <Button
                              key={server.id}
                              variant="link"
                              size="sm"
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
                )}
              </AlertDescription>
            </Alert>
            <div className="flex gap-2 mt-4">
              <Button size="sm" variant="outline" onClick={() => navigate('/overview')}>
                返回总览
              </Button>
              {isServerNotFound && availableServers.length > 0 && (
                <Button size="sm" onClick={() => navigate(`/server/${availableServers[0].id}`)}>
                  访问 {availableServers[0].name}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isLoading || !hasServerInfo || !serverInfo) {
    return <LoadingSpinner height="16rem" />
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="概览"
        icon={<LayoutDashboard className="h-5 w-5" />}
        serverTag={serverInfo.name}
        actions={
          <ServerOperationButtons
            serverId={id}
            serverName={serverInfo.name}
            status={status}
          />
        }
      />

      <OnlinePlayersCard
        serverId={id}
        isHealthy={isHealthy || false}
      />

      <ServerResourcesCard
        cpuPercentage={cpu?.cpuPercentage}
        memoryUsageBytes={memory?.memoryUsageBytes}
        serverInfo={serverInfo}
        isRunning={isRunning || false}
        hasCpuData={hasCpuData || false}
        hasMemoryData={hasMemoryData || false}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ServerAddressCard serverId={id} />
        <ServerInfoCard serverInfo={serverInfo} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
        <ServerRestartScheduleCard
          restartSchedule={restartSchedule}
          isLoading={restartScheduleQuery?.isLoading}
        />
        <ServerDiskUsageCard
          diskUsageBytes={diskUsage?.diskUsageBytes}
          diskTotalBytes={diskUsage?.diskTotalBytes}
          diskAvailableBytes={diskUsage?.diskAvailableBytes}
          hasDiskUsageData={hasDiskUsageData || false}
        />
      </div>

      <ServerIOStatsCard
        diskReadBytes={iostats?.diskReadBytes}
        diskWriteBytes={iostats?.diskWriteBytes}
        networkReceiveBytes={iostats?.networkReceiveBytes}
        networkSendBytes={iostats?.networkSendBytes}
        isRunning={isRunning || false}
        hasIOStatsData={hasIOStatsData || false}
      />
    </div>
  )
}

export default ServerDetail
