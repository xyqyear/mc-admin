import React from 'react'
import {
  Card,
  Table,
  Button,
  Progress,
  Modal,
  Alert,
  Space,
  Tooltip,
  App,
  type TableProps
} from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  PlayCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  DeleteOutlined,
  PlusOutlined,
  DownOutlined,
  DashboardOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import SimpleMetricCard from '@/components/overview/SimpleMetricCard'
import ProgressMetricCard from '@/components/overview/ProgressMetricCard'
import ServerCountCard from '@/components/overview/ServerCountCard'
import ServerStateTag from '@/components/overview/ServerStateTag'
import type { ServerStatus } from '@/types/Server'
import { useOverviewData } from '@/hooks/queries/page/useOverviewData'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useAutoUpdateDNS } from '@/hooks/mutations/useDnsMutations'
import { serverStatusUtils } from '@/utils/serverUtils'
import { useServerOperationConfirm } from '@/components/modals/ServerOperationConfirmModal'

const Overview: React.FC = () => {
  const navigate = useNavigate()
  const { message } = App.useApp()

  // 使用新的数据架构 - 通过分离查询获取完整数据
  const {
    enrichedServers, // 包含所有运行时数据的完整服务器列表
    systemInfo,
    systemCpuPercent, // 新的分离的系统CPU百分比数据
    systemDiskUsage, // 新的系统磁盘使用数据
    backupRepositoryUsage, // 新的备份仓库使用数据
    serverNum,
    runningServers,
    onlinePlayerNum,
    isLoading,
    isStatusLoading,
    isError,
    error,
    refetch
  } = useOverviewData()

  const { useServerOperation, useDeleteRestartSchedule } = useServerMutations()
  const serverOperationMutation = useServerOperation()
  const deleteRestartScheduleMutation = useDeleteRestartSchedule({ silent: true })
  const autoUpdateDNS = useAutoUpdateDNS()

  const { showConfirm } = useServerOperationConfirm()


  const isOperationAvailable = (operation: string, status: ServerStatus) => {
    return serverStatusUtils.isOperationAvailable(operation, status)
  }

  // 智能启动：根据服务器状态决定使用 start 还是 up
  const handleStartServer = (serverId: string, status: ServerStatus) => {
    const server = enrichedServers.find(s => s.id === serverId)
    if (!server) return

    // 根据状态决定操作类型
    const operation = status === 'CREATED' ? 'start' : 'up'
    const operationText = status === 'CREATED' ? '启动' : '启动(up)'

    Modal.confirm({
      title: '确认启动',
      content: `确定要${operationText}服务器 "${server.name}" 吗？`,
      okText: `确认${operationText}`,
      okType: 'primary',
      cancelText: '取消',
      onOk: () => {
        serverOperationMutation.mutate({ action: operation, serverId })
      }
    })
  }

  const handleServerOperation = (operation: string, serverId: string) => {
    // 使用新的确认组件处理所有需要确认的操作
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

            // 如果是删除操作，在成功后执行后续操作
            if (action === 'remove') {
              // 删除重启计划
              try {
                await deleteRestartScheduleMutation.mutateAsync(serverIdParam)
                message.success(`服务器 "${serverIdParam}" 重启计划删除成功`)
              } catch (scheduleError: any) {
                // 重启计划删除失败不影响服务器删除
                message.warning(`服务器 "${serverIdParam}" 删除成功，但重启计划删除失败: ${scheduleError.message || '未知错误'}`)
              }

              // 触发DNS更新
              try {
                await autoUpdateDNS.mutateAsync()
              } catch (dnsError: any) {
                // DNS更新失败不影响删除操作，错误已在mutation中处理
                console.warn('DNS自动更新失败:', dnsError)
              }
            }
          } catch (error: any) {
            // 操作失败，错误已在mutation中处理
            console.error('服务器操作失败:', error)
          }
        }
      })
      return
    }

    // 其他操作直接执行
    serverOperationMutation.mutate({ action: operation, serverId })
  }

  // 构建表格数据 - 直接使用包含完整运行时数据的enrichedServers
  const tableData = enrichedServers.map(server => ({
    id: server.id,
    name: server.name,
    serverType: server.serverType,
    gameVersion: server.gameVersion,
    gamePort: server.gamePort,
    maxMemoryBytes: server.maxMemoryBytes,
    status: server.status,
    onlinePlayers: server.onlinePlayers,
    maxPlayers: 20, // 默认值，后续可从配置获取
    cpuPercentage: server.cpuPercentage,
    memoryUsageBytes: server.memoryUsageBytes,
    diskUsageBytes: server.diskUsageBytes,
    diskTotalBytes: server.diskTotalBytes,
    diskAvailableBytes: server.diskAvailableBytes,
  }))

  const columns: TableProps<typeof tableData[0]>['columns'] = [
    {
      title: '服务器',
      dataIndex: 'name',
      key: 'name',
      width: 100,
      render: (name: string, record: typeof tableData[0]) => (
        <div>
          <div className="font-semibold">{name}</div>
          <div className="text-xs text-gray-500">
            {record.serverType} {record.gameVersion}
          </div>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: ServerStatus) => (
        <ServerStateTag state={status} />
      ),
    },
    {
      title: '玩家',
      key: 'players',
      width: 120,
      render: (_: any, record: typeof tableData[0]) => (
        <div className="text-center">
          <div className="font-semibold">
            {record.onlinePlayers.length}/{record.maxPlayers}
          </div>
          {record.onlinePlayers.length > 0 && (
            <div className="text-xs text-gray-500">
              {record.onlinePlayers.join(', ')}
            </div>
          )}
        </div>
      ),
    },
    {
      title: '资源',
      key: 'resources',
      width: 150,
      render: (_: any, record: typeof tableData[0]) => {
        const hasRuntimeData = record.cpuPercentage != null || record.memoryUsageBytes != null
        const hasDiskData = record.diskUsageBytes != null

        if (!hasRuntimeData && !hasDiskData) {
          return <span className="text-gray-400">暂无数据</span>
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
                  <span>CPU:</span>
                  <Progress
                    percent={cpuPercentage}
                    size="small"
                    style={{ width: 60 }}
                    showInfo={false}
                    strokeColor={cpuPercentage > 80 ? '#ff4d4f' : cpuPercentage > 60 ? '#faad14' : '#52c41a'}
                  />
                  <span className="text-gray-500">{cpuPercentage.toFixed(1)}%</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span>内存:</span>
                  <Progress
                    percent={memoryPercent}
                    size="small"
                    style={{ width: 60 }}
                    showInfo={false}
                    strokeColor={memoryPercent > 80 ? '#ff4d4f' : memoryPercent > 60 ? '#faad14' : '#52c41a'}
                  />
                  <span className="text-gray-500">{(memoryUsageMB / 1024).toFixed(1)}GB</span>
                </div>
              </>
            )}
            {hasDiskData && record.diskTotalBytes && (
              <div className="flex items-center gap-2 text-xs">
                <span>磁盘:</span>
                <Progress
                  percent={((record.diskTotalBytes - record.diskAvailableBytes!) / record.diskTotalBytes) * 100}
                  success={{
                    percent: (record.diskUsageBytes! / record.diskTotalBytes) * 100,
                    strokeColor: '#52c41a'
                  }}
                  size="small"
                  style={{ width: 60 }}
                  showInfo={false}
                  strokeColor="#faad14"
                />
                <span className="text-gray-500">
                  {(record.diskUsageBytes! / (1024 ** 3)).toFixed(1)}/{(record.diskAvailableBytes! / (1024 ** 3)).toFixed(1)}/{(record.diskTotalBytes / (1024 ** 3)).toFixed(1)}GB
                </span>
              </div>
            )}
            {hasDiskData && !record.diskTotalBytes && (
              <div className="flex items-center gap-2 text-xs">
                <span>磁盘:</span>
                <span className="text-gray-500 ml-auto">
                  {(record.diskUsageBytes! / (1024 ** 3)).toFixed(1)}GB
                </span>
              </div>
            )}
          </div>
        )
      },
    },
    {
      title: '端口',
      dataIndex: 'gamePort',
      key: 'gamePort',
      width: 80,
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: any, record: typeof tableData[0]) => (
        <Space>
          <Tooltip title="启动服务器">
            <Button
              icon={<PlayCircleOutlined />}
              size="small"
              type={record.status === 'CREATED' || record.status === 'EXISTS' ? 'primary' : 'default'}
              disabled={!isOperationAvailable('start', record.status) && !isOperationAvailable('up', record.status)}
              loading={serverOperationMutation.isPending}
              onClick={() => handleStartServer(record.id, record.status)}
            />
          </Tooltip>
          <Tooltip title="停止服务器">
            <Button
              icon={<StopOutlined />}
              size="small"
              danger
              disabled={!isOperationAvailable('stop', record.status)}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('stop', record.id)}
            />
          </Tooltip>
          <Tooltip title="重启服务器">
            <Button
              icon={<ReloadOutlined />}
              size="small"
              danger
              disabled={!isOperationAvailable('restart', record.status)}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('restart', record.id)}
            />
          </Tooltip>
          <Tooltip title="下线服务器">
            <Button
              icon={<DownOutlined />}
              size="small"
              danger
              disabled={!isOperationAvailable('down', record.status)}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('down', record.id)}
            />
          </Tooltip>
          <Tooltip title="服务器详情">
            <Button
              icon={<DashboardOutlined />}
              size="small"
              type="primary"
              onClick={() => navigate(`/server/${record.id}`)}
            />
          </Tooltip>
          <Tooltip title="控制台">
            <Button
              icon={<CodeOutlined />}
              size="small"
              onClick={() => navigate(`/server/${record.id}/console`)}
            />
          </Tooltip>
          <Tooltip title="删除服务器">
            <Button
              icon={<DeleteOutlined />}
              size="small"
              danger
              disabled={!isOperationAvailable('remove', record.status)}
              loading={serverOperationMutation.isPending}
              onClick={() => handleServerOperation('remove', record.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* 系统概览卡片 */}
      <div className="grid gap-3 sm:gap-4" style={{
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
      }}>
        <div className="h-[240px] flex" style={{ minWidth: '200px' }}>
          <ServerCountCard totalServers={serverNum} runningServers={runningServers} />
        </div>
        <div className="h-[240px] flex" style={{ minWidth: '200px' }}>
          <SimpleMetricCard value={onlinePlayerNum} title="在线玩家" />
        </div>
        <div className="h-[240px] flex" style={{ minWidth: '200px' }}>
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
        <div className="h-[240px] flex" style={{ minWidth: '200px' }}>
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
        <div className="h-[240px] flex" style={{ minWidth: '200px' }}>
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
        <div className="h-[240px] flex" style={{ minWidth: '200px' }}>
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

      {/* 错误提示 */}
      {isError && (
        <Alert
          title="加载数据失败"
          description={error?.message || '发生未知错误'}
          type="error"
          showIcon
          closable
          action={
            <Button size="small" danger onClick={refetch}>
              重试
            </Button>
          }
        />
      )}

      {/* 服务器表格 */}
      <Card
        title="Minecraft 服务器"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/server/new')}
          >
            创建服务器
          </Button>
        }
      >
        <Table
          dataSource={tableData}
          columns={columns}
          rowKey="id"
          scroll={{ x: 'max-content' }}
          loading={isLoading || isStatusLoading}
          pagination={false}
        />
      </Card>
    </div>
  )
}

export default Overview
