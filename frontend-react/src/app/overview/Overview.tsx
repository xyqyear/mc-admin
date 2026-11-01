import React, { useState } from 'react'
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

import { Card, CardHeader, CardTitle, CardContent } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { ButtonLink } from '@/shared/components/ButtonLink'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { SampleValue } from '@/features/monitoring/ui/SampleValue'
import { Spinner } from '@/shared/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/ui/table'

import SimpleMetricCard from '@/app/overview/components/SimpleMetricCard'
import ProgressMetricCard from '@/app/overview/components/ProgressMetricCard'
import ServerCountCard from '@/app/overview/components/ServerCountCard'
import ServerStateTag from '@/features/servers/ui/ServerStateTag'
import type { ServerStatus } from '@/features/servers/contracts'
import { useOverviewData } from '@/app/overview/useOverviewData'
import { useServerOperation } from '@/features/servers/commands';
import { useCurrentUser } from '@/features/users/queries'
import { UserRole } from '@/features/users/contracts'
import { serverStatusUtils } from '@/features/servers/presentation'
import SyncWithFilesystemDialog from '@/features/servers/ui/SyncWithFilesystemDialog'
import { useServerOperationConfirm } from '@/features/servers/ui/ServerOperationConfirmDialog'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { openTaskCenter } from '@/features/tasks/commands'

const Overview: React.FC = () => {
  const {
    enrichedServers,
    system,
    monitoringFailed,
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
  const serverOperationMutation = useServerOperation()

  const { data: currentUser } = useCurrentUser()
  const isOwner = currentUser?.role === UserRole.OWNER

  const [isSyncDialogOpen, setIsSyncDialogOpen] = useState(false)

  const { showConfirm, confirmDialog } = useServerOperationConfirm()
  const { confirm: confirmStart, confirmDialog: startConfirmDialog } = useConfirm()

  const isOperationAvailable = (operation: string, status: ServerStatus) => {
    return serverStatusUtils.isOperationAvailable(operation, status)
  }

  const handleStartServer = (serverId: string) => {
    const server = enrichedServers.find(s => s.id === serverId)
    if (!server) return

    confirmStart({
      title: '确认启动',
      description: `确定要启动服务器 "${server.name}" 吗？`,
      confirmText: '确认启动',
      cancelText: '取消',
      onConfirm: () => {
        serverOperationMutation.mutate({ action: 'start', serverId })
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
    maintenance: server.maintenance,
    taskId: server.maintenance?.task_id ?? (serverOperationMutation.isPending && serverOperationMutation.variables?.serverId === server.id ? serverOperationMutation.taskId : null),
    pending: serverOperationMutation.isPending || !!server.maintenance?.task_id,
    reason: server.maintenance?.active ? server.maintenance.description : serverOperationMutation.isPending && serverOperationMutation.variables?.serverId === server.id ? '正在提交并等待操作完成' : null,
    onlinePlayers: server.onlinePlayers,
    maxPlayers: 20,
    samples: server.samples,
  }))

  const renderResources = (record: typeof tableData[0]) => (
    <div className="space-y-1 text-xs">
      <div>CPU：<SampleValue sample={record.samples?.cpu_percent} failed={monitoringFailed}>{value => `${value.toFixed(1)}%`}</SampleValue></div>
      <div>内存：<SampleValue sample={record.samples?.memory_bytes} failed={monitoringFailed}>{value => `${(value / 1024 ** 3).toFixed(1)}GB`}</SampleValue></div>
      <div>存档：<SampleValue sample={record.samples?.disk} failed={monitoringFailed}>{value => `${(value.used / 1024 ** 3).toFixed(1)}GB`}</SampleValue></div>
    </div>
  )
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:gap-4 grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
        <div className="h-60 flex min-w-50">
          <ServerCountCard totalServers={serverNum} runningServers={runningServers} />
        </div>
        <div className="h-60 flex min-w-50">
          <SimpleMetricCard value={onlinePlayerNum} title="在线玩家" />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={system?.cpu_percent.value ?? null} sample={system?.cpu_percent} failed={monitoringFailed}
            title="CPU使用率"
            extraInfo={
              system?.load.value ? `负载: ${system.load.value.map(value => value.toFixed(2)).join(" ")}`
                : '-'
            }
          />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={
              system?.memory.value ? (system.memory.value.used / system.memory.value.total) * 100
                : null
            }
            title="内存使用率" sample={system?.memory} failed={monitoringFailed}
            extraInfo={
              system?.memory.value ? `${(system.memory.value.used / 1024 ** 3).toFixed(1)}/${(system.memory.value.total / 1024 ** 3).toFixed(1)}GB`
                : '-'
            }
          />
        </div>
        <div className="h-60 flex min-w-50">
          <ProgressMetricCard
            value={
              system?.disk.value ? (system.disk.value.used / system.disk.value.total) * 100
                : null
            }
            title="存储使用率" sample={system?.disk} failed={monitoringFailed}
            extraInfo={
              system?.disk.value ? `${(system.disk.value.used / 1024 ** 3).toFixed(1)}/${(system.disk.value.total / 1024 ** 3).toFixed(1)}GB`
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
              <ButtonLink to="/server/new">
                <Plus className="mr-1 h-4 w-4" />
                创建服务器
              </ButtonLink>
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
                            disabled={record.pending || record.maintenance?.active || !isOperationAvailable('start', record.status)}
                            onClick={() => handleStartServer(record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <Play className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="停止服务器"
                            disabled={record.pending || !isOperationAvailable('stop', record.status)}
                            onClick={() => handleServerOperation('stop', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <Square className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="重启服务器"
                            disabled={record.pending || record.maintenance?.active || !isOperationAvailable('restart', record.status)}
                            onClick={() => handleServerOperation('restart', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <RotateCw className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="下线服务器"
                            disabled={record.pending || !isOperationAvailable('down', record.status)}
                            onClick={() => handleServerOperation('down', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                          </Button>
                          <ButtonLink
                            variant="default"
                            size="icon"
                            className="h-7 w-7"
                            title="服务器详情"
                            to={`/server/${record.id}`}
                          >
                            <LayoutDashboard className="h-3.5 w-3.5" />
                          </ButtonLink>
                          <ButtonLink
                            variant="outline"
                            size="icon"
                            className="h-7 w-7"
                            title="控制台"
                            to={`/server/${record.id}/console`}
                          >
                            <Terminal className="h-3.5 w-3.5" />
                          </ButtonLink>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            title="删除服务器"
                            disabled={record.pending || record.maintenance?.active || !isOperationAvailable('remove', record.status)}
                            onClick={() => handleServerOperation('remove', record.id)}
                          >
                            {serverOperationMutation.isPending ? <Spinner className="size-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
                          </Button>
                        </div>
                        {record.reason && <div role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{record.reason}</span>
                          {record.taskId && <Button variant="link" size="sm" onClick={openTaskCenter}>查看任务</Button>}
                        </div>}
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
