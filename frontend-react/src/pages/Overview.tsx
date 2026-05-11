import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  Square,
  RotateCw,
  Trash2,
  Plus,
  ChevronDown,
  LayoutDashboard,
  Terminal,
  ArrowRightLeft,
} from 'lucide-react'

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import SimpleMetricCard from '@/components/overview/SimpleMetricCard'
import ProgressMetricCard from '@/components/overview/ProgressMetricCard'
import ServerCountCard from '@/components/overview/ServerCountCard'
import ServerStateTag from '@/components/overview/ServerStateTag'
import type { ServerStatus } from '@/types/Server'
import { useOverviewData } from '@/hooks/queries/page/useOverviewData'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useCurrentUser } from '@/hooks/queries/base/useUserQueries'
import { UserRole } from '@/types/User'
import { serverStatusUtils } from '@/utils/serverUtils'
import SyncWithFilesystemDialog from '@/components/dialogs/SyncWithFilesystemDialog'
import { useServerOperationConfirm } from '@/components/dialogs/ServerOperationConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'

const gradientIndicatorStyle = (percent: number): React.CSSProperties => {
  const clamped = Math.max(0, Math.min(100, percent))
  const hue = 120 - (clamped / 100) * 120
  return { '--indicator-color': `hsl(${hue} 70% 45%)` } as React.CSSProperties
}

const Overview: React.FC = () => {
  const navigate = useNavigate()

  const {
    enrichedServers,
    systemInfo,
    systemCpuPercent,
    systemDiskUsage,
    backupRepositoryUsage,
    serverNum,
    runningServers,
    onlinePlayerNum,
    isLoading,
    isStatusLoading,
    isError,
    error,
    refetch,
  } = useOverviewData()

  const { useServerOperation } = useServerMutations()
  const serverOperationMutation = useServerOperation()

  const { data: currentUser } = useCurrentUser()
  const isOwner = currentUser?.role === UserRole.OWNER

  const [isSyncDialogOpen, setIsSyncDialogOpen] = useState(false)

  const { showConfirm, confirmDialog } = useServerOperationConfirm()
  const { confirm: confirmStart, confirmDialog: startConfirmDialog } = useConfirm()

  const isOperationAvailable = (operation: string, status: ServerStatus) => {
    return serverStatusUtils.isOperationAvailable(operation, status)
  }

  const handleStartServer = (serverId: string, status: ServerStatus) => {
    const server = enrichedServers.find(s => s.id === serverId)
    if (!server) return

    const operation = status === 'CREATED' ? 'start' : 'up'
    const operationText = status === 'CREATED' ? '启动' : '启动(up)'

    confirmStart({
      title: '确认启动',
      description: `确定要${operationText}服务器 "${server.name}" 吗？`,
      confirmText: `确认${operationText}`,
      cancelText: '取消',
      onConfirm: () => {
        serverOperationMutation.mutate({ action: operation, serverId })
      },
    })
  }

  const handleServerOperation = (operation: string, serverId: string) => {
    if (operation === 'stop' || operation === 'restart' || operation === 'down' || operation === 'remove') {
      const server = enrichedServers.find(s => s.id === serverId)
      if (!server) return

      showConfirm({
        operation: operation as 'stop' | 'restart' | 'down' | 'remove',
        serverName: server.name,
        serverId,
        onConfirm: async (action, serverIdParam) => {
          try {
            // Backend bundles remove + cron cancellation + DNS update
            // into a single round-trip — no chained requests needed.
            await serverOperationMutation.mutateAsync({ action, serverId: serverIdParam })
          } catch (error: any) {
            console.error('服务器操作失败:', error)
          }
        },
      })
      return
    }

    serverOperationMutation.mutate({ action: operation, serverId })
  }

  const tableData = enrichedServers.map(server => ({
    id: server.id,
    name: server.name,
    serverType: server.serverType,
    gameVersion: server.gameVersion,
    gamePort: server.gamePort,
    maxMemoryBytes: server.maxMemoryBytes,
    status: server.status,
    onlinePlayers: server.onlinePlayers,
    maxPlayers: 20,
    cpuPercentage: server.cpuPercentage,
    memoryUsageBytes: server.memoryUsageBytes,
    diskUsageBytes: server.diskUsageBytes,
    diskTotalBytes: server.diskTotalBytes,
    diskAvailableBytes: server.diskAvailableBytes,
  }))

  const renderResources = (record: typeof tableData[0]) => {
    const hasRuntimeData = record.cpuPercentage != null || record.memoryUsageBytes != null
    const hasDiskData = record.diskUsageBytes != null

    if (!hasRuntimeData && !hasDiskData) {
      return <span className="text-muted-foreground">暂无数据</span>
    }

    const cpuPercentage = record.cpuPercentage || 0
    const memoryUsageBytes = record.memoryUsageBytes || 0
    const memoryUsageMB = memoryUsageBytes / (1024 * 1024)
    const memoryLimitMB = record.maxMemoryBytes / (1024 * 1024)
    const memoryPercent = memoryLimitMB > 0 ? (memoryUsageMB / memoryLimitMB) * 100 : 0

    return (
      <div className="space-y-1">
        {hasRuntimeData && (
          <>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-8">CPU:</span>
              <Progress
                value={cpuPercentage}
                className="w-15 **:data-[slot=progress-indicator]:bg-(--indicator-color)"
                style={gradientIndicatorStyle(cpuPercentage)}
              />
              <span className="text-muted-foreground">{cpuPercentage.toFixed(1)}%</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-8">内存:</span>
              <Progress
                value={memoryPercent}
                className="w-15 **:data-[slot=progress-indicator]:bg-(--indicator-color)"
                style={gradientIndicatorStyle(memoryPercent)}
              />
              <span className="text-muted-foreground">{(memoryUsageMB / 1024).toFixed(1)}GB</span>
            </div>
          </>
        )}
        {hasDiskData && record.diskTotalBytes && (
          <div className="flex items-center gap-2 text-xs">
            <span className="w-8">磁盘:</span>
            <div className="h-1 w-15 rounded-full bg-muted overflow-hidden flex">
              <div
                className="h-full bg-green-500 transition-all"
                style={{ width: `${(record.diskUsageBytes! / record.diskTotalBytes) * 100}%` }}
              />
              <div
                className="h-full bg-yellow-500 transition-all"
                style={{ width: `${((record.diskTotalBytes - record.diskAvailableBytes! - record.diskUsageBytes!) / record.diskTotalBytes) * 100}%` }}
              />
            </div>
            <span className="text-muted-foreground">
              {(record.diskUsageBytes! / (1024 ** 3)).toFixed(1)}/{(record.diskAvailableBytes! / (1024 ** 3)).toFixed(1)}/{(record.diskTotalBytes / (1024 ** 3)).toFixed(1)}GB
            </span>
          </div>
        )}
        {hasDiskData && !record.diskTotalBytes && (
          <div className="flex items-center gap-2 text-xs">
            <span className="w-8">磁盘:</span>
            <span className="text-muted-foreground ml-auto">
              {(record.diskUsageBytes! / (1024 ** 3)).toFixed(1)}GB
            </span>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* System overview cards */}
      <div className="grid gap-3 sm:gap-4 grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
        <div className="h-60 flex min-w-50">
          <ServerCountCard totalServers={serverNum} runningServers={runningServers} />
        </div>
        <div className="h-60 flex min-w-50">
          <SimpleMetricCard value={onlinePlayerNum} title="在线玩家" />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={systemCpuPercent ?? 0}
            title="CPU使用率"
            extraInfo={
              systemInfo
                ? `负载: ${systemInfo.cpuLoad1Min.toFixed(2)} ${systemInfo.cpuLoad5Min.toFixed(2)} ${systemInfo.cpuLoad15Min.toFixed(2)}`
                : '-'
            }
          />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={
              systemInfo
                ? (systemInfo.ramUsedGB / systemInfo.ramTotalGB) * 100
                : 0
            }
            title="内存使用率"
            extraInfo={
              systemInfo
                ? `${systemInfo.ramUsedGB.toFixed(1)}/${systemInfo.ramTotalGB.toFixed(1)}GB`
                : '-'
            }
          />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={
              systemDiskUsage
                ? (systemDiskUsage.diskUsedGB / systemDiskUsage.diskTotalGB) * 100
                : 0
            }
            title="存储使用率"
            extraInfo={
              systemDiskUsage
                ? `${systemDiskUsage.diskUsedGB.toFixed(1)}/${systemDiskUsage.diskTotalGB.toFixed(1)}GB`
                : '-'
            }
          />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={
              backupRepositoryUsage
                ? (backupRepositoryUsage.backupUsedGB / backupRepositoryUsage.backupTotalGB) * 100
                : 0
            }
            title="备份使用率"
            extraInfo={
              backupRepositoryUsage
                ? `${backupRepositoryUsage.backupUsedGB.toFixed(1)}/${backupRepositoryUsage.backupTotalGB.toFixed(1)}GB`
                : backupRepositoryUsage === null ? '备份未配置' : '-'
            }
          />
        </div>
      </div>

      {/* Error alert */}
      {isError && (
        <Alert variant="destructive">
          <AlertTitle>加载数据失败</AlertTitle>
          <AlertDescription>
            <div className="flex items-center justify-between">
              <span>{error?.message || '发生未知错误'}</span>
              <Button size="sm" variant="destructive" onClick={refetch}>
                重试
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}

      {/* Server table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Minecraft 服务器</CardTitle>
            <div className="flex items-center gap-2">
              {isOwner && (
                <Button
                  variant="outline"
                  onClick={() => setIsSyncDialogOpen(true)}
                  title="对比文件系统与数据库记录"
                >
                  <ArrowRightLeft className="mr-1 h-4 w-4" />
                  与文件系统同步
                </Button>
              )}
              <Button onClick={() => navigate('/server/new')}>
                <Plus className="mr-1 h-4 w-4" />
                创建服务器
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {(isLoading || isStatusLoading) ? (
            <div className="flex justify-center py-8">
              <Spinner className="size-8" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>服务器</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>玩家</TableHead>
                  <TableHead>资源</TableHead>
                  <TableHead>端口</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tableData.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                      暂无服务器
                    </TableCell>
                  </TableRow>
                ) : (
                  tableData.map(record => (
                    <TableRow key={record.id}>
                      <TableCell>
                        <div className="font-semibold">{record.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {record.serverType} {record.gameVersion}
                        </div>
                      </TableCell>

                      <TableCell>
                        <ServerStateTag state={record.status} />
                      </TableCell>

                      <TableCell>
                        <div className="text-center">
                          <div className="font-semibold">
                            {record.onlinePlayers.length}/{record.maxPlayers}
                          </div>
                          {record.onlinePlayers.length > 0 && (
                            <div className="text-xs text-muted-foreground">
                              {record.onlinePlayers.join(', ')}
                            </div>
                          )}
                        </div>
                      </TableCell>

                      <TableCell>{renderResources(record)}</TableCell>

                      <TableCell>{record.gamePort}</TableCell>

                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button
                            variant={record.status === 'CREATED' || record.status === 'EXISTS' ? 'default' : 'outline'}
                            size="icon"
                            className="h-7 w-7"
                            title="启动服务器"
                            disabled={serverOperationMutation.isPending || (!isOperationAvailable('start', record.status) && !isOperationAvailable('up', record.status))}
                            onClick={() => handleStartServer(record.id, record.status)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <Play className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="停止服务器"
                            disabled={serverOperationMutation.isPending || !isOperationAvailable('stop', record.status)}
                            onClick={() => handleServerOperation('stop', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <Square className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="重启服务器"
                            disabled={serverOperationMutation.isPending || !isOperationAvailable('restart', record.status)}
                            onClick={() => handleServerOperation('restart', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <RotateCw className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="下线服务器"
                            disabled={serverOperationMutation.isPending || !isOperationAvailable('down', record.status)}
                            onClick={() => handleServerOperation('down', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="default"
                            size="icon"
                            className="h-7 w-7"
                            title="服务器详情"
                            onClick={() => navigate(`/server/${record.id}`)}
                          >
                            <LayoutDashboard className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7"
                            title="控制台"
                            onClick={() => navigate(`/server/${record.id}/console`)}
                          >
                            <Terminal className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="删除服务器"
                            disabled={serverOperationMutation.isPending || !isOperationAvailable('remove', record.status)}
                            onClick={() => handleServerOperation('remove', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {confirmDialog}
      {startConfirmDialog}
      <SyncWithFilesystemDialog
        open={isSyncDialogOpen}
        onClose={() => setIsSyncDialogOpen(false)}
      />
    </div>
  )
}

export default Overview
