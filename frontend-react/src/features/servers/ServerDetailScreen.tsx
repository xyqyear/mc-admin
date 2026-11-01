import React from 'react'
import { useParams } from 'react-router'
import { LayoutDashboard } from 'lucide-react'
import { Card, CardContent } from '@/shared/ui/card'
import { ButtonLink } from '@/shared/components/ButtonLink'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import LoadingSpinner from '@/shared/layout/LoadingSpinner'
import PageHeader from '@/shared/layout/PageHeader'
import ServerOperationButtons from '@/features/servers/ui/ServerOperationButtons'
import ServerAddressCard from '@/features/servers/ui/ServerAddressCard'
import ServerInfoCard from '@/features/servers/ui/ServerInfoCard'
import ServerDiskUsageCard from '@/features/servers/ui/ServerDiskUsageCard'
import ServerResourcesCard from '@/features/servers/ui/ServerResourcesCard'
import ServerIOStatsCard from '@/features/servers/ui/ServerIOStatsCard'
import OnlinePlayersCard from '@/features/players/ui/OnlinePlayersCard'
import ServerRestartScheduleCard from '@/features/servers/ui/ServerRestartScheduleCard'
import { useServerDetailData } from '@/features/servers/useServerDetailData'
import { useServers } from '@/features/servers/queries';

const ServerDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const allServersQuery = useServers()

  const {
    serverInfo,
    status,
    samples,
    monitoringFailed,
    restartSchedule,
    restartScheduleQuery,
    isLoading,
    isError,
    error,
    hasServerInfo,
    isHealthy,
  } = useServerDetailData(id || '')

  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert variant="destructive">
          <AlertTitle>参数错误</AlertTitle>
          <AlertDescription>
            <div className="flex items-center justify-between">
              <span>缺少服务器ID参数</span>
              <ButtonLink size="sm" variant="outline" to="/overview">
                返回总览
              </ButtonLink>
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
                            <ButtonLink
                              key={server.id}
                              variant="link"
                              size="sm"
                              className="block text-left p-0 h-auto"
                              to={`/server/${server.id}`}
                            >
                              {server.name} ({server.id})
                            </ButtonLink>
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
              <ButtonLink size="sm" variant="outline" to="/overview">
                返回总览
              </ButtonLink>
              {isServerNotFound && availableServers.length > 0 && (
                <ButtonLink size="sm" to={`/server/${availableServers[0].id}`}>
                  访问 {availableServers[0].name}
                </ButtonLink>
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
        cpu={samples?.cpu_percent}
        memory={samples?.memory_bytes}
        serverInfo={serverInfo}
        failed={monitoringFailed}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ServerAddressCard serverId={id} />
        <ServerInfoCard serverInfo={serverInfo} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
        <ServerRestartScheduleCard
          serverId={id}
          restartSchedule={restartSchedule}
          isLoading={restartScheduleQuery?.isLoading}
          error={restartScheduleQuery.error}
        />
        <ServerDiskUsageCard
          sample={samples?.disk}
          failed={monitoringFailed}
        />
      </div>

      <ServerIOStatsCard
        disk={samples?.disk_io}
        network={samples?.network_io}
        failed={monitoringFailed}
      />
    </div>
  )
}

export default ServerDetail
