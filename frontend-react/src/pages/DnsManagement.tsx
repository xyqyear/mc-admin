import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  Globe,
  RotateCw,
  RefreshCw,
  Settings,
  Share2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react'
import {
  type ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'

import PageHeader from '@/components/layout/PageHeader'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import { DataTable } from '@/components/common/DataTable'
import { useDNSStatus, useDNSEnabled, useDNSRecords, useRouterRoutes } from '@/hooks/queries/base/useDnsQueries'
import { useUpdateDNS, useRefreshDNSData } from '@/hooks/mutations/useDnsMutations'
import type { DNSRecord } from '@/types/Dns'

// --- Column definitions ---

const dnsRecordsColumns: ColumnDef<DNSRecord, any>[] = [
  {
    accessorKey: 'sub_domain',
    header: '子域名',
    size: 200,
  },
  {
    accessorKey: 'record_type',
    header: '记录类型',
    size: 100,
    cell: ({ row }) => {
      const type = row.getValue<string>('record_type')
      const colorClass =
        type === 'A' ? 'bg-blue-100 text-blue-800 hover:bg-blue-100' :
        type === 'AAAA' ? 'bg-green-100 text-green-800 hover:bg-green-100' :
        type === 'SRV' ? 'bg-orange-100 text-orange-800 hover:bg-orange-100' :
        ''
      return <Badge className={colorClass}>{type}</Badge>
    },
  },
  {
    accessorKey: 'value',
    header: '值',
    cell: ({ row }) => (
      <span className="truncate block" title={row.getValue<string>('value')}>
        {row.getValue<string>('value')}
      </span>
    ),
  },
  {
    accessorKey: 'ttl',
    header: 'TTL',
    size: 80,
    cell: ({ row }) => `${row.getValue<number>('ttl')}s`,
  },
  {
    accessorKey: 'record_id',
    header: '记录ID',
    size: 120,
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground truncate block" title={String(row.getValue('record_id'))}>
        {String(row.getValue('record_id'))}
      </span>
    ),
  },
]

interface RouterRouteRow {
  key: string
  server_address: string
  backend: string
}

const routerRoutesColumns: ColumnDef<RouterRouteRow, any>[] = [
  {
    accessorKey: 'server_address',
    header: '服务器地址',
    cell: ({ row }) => (
      <span className="truncate block" title={row.getValue<string>('server_address')}>
        {row.getValue<string>('server_address')}
      </span>
    ),
  },
  {
    accessorKey: 'backend',
    header: '后端地址',
    size: 150,
  },
]

// --- Main component ---

const DnsManagement: React.FC = () => {
  const navigate = useNavigate()

  // Queries
  const { data: dnsEnabled, isLoading: enabledLoading } = useDNSEnabled()
  const isDNSEnabled = dnsEnabled?.enabled ?? false
  const { data: dnsStatus, isLoading: statusLoading, error: statusError } = useDNSStatus(isDNSEnabled)
  const { data: dnsRecords, isLoading: recordsLoading, error: recordsError } = useDNSRecords(isDNSEnabled)
  const { data: routerRoutes, isLoading: routesLoading, error: routesError } = useRouterRoutes(isDNSEnabled)

  // Mutations
  const updateDNSMutation = useUpdateDNS()
  const refreshDataMutation = useRefreshDNSData()

  const handleRefresh = () => {
    refreshDataMutation.mutate()
  }

  const handleUpdate = () => {
    if (!dnsEnabled?.enabled) {
      toast.warning('DNS管理器未启用，无法执行更新操作')
      return
    }
    updateDNSMutation.mutate()
  }

  const handleGoToSettings = () => {
    navigate('/config?module=dns')
  }

  // Router routes table data
  const routerRoutesData = useMemo(() => {
    if (!routerRoutes) return []
    return Object.entries(routerRoutes).map(([server_address, backend]) => ({
      key: server_address,
      server_address,
      backend,
    }))
  }, [routerRoutes])

  // TanStack Table instances
  const [dnsPagination, setDnsPagination] = useState({ pageIndex: 0, pageSize: 20 })
  const [routesPagination, setRoutesPagination] = useState({ pageIndex: 0, pageSize: 20 })

  const dnsTable = useReactTable({
    data: dnsRecords ?? [],
    columns: dnsRecordsColumns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onPaginationChange: setDnsPagination,
    state: { pagination: dnsPagination },
    autoResetPageIndex: false,
    getRowId: (row) => String(row.record_id),
  })

  const routesTable = useReactTable({
    data: routerRoutesData,
    columns: routerRoutesColumns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onPaginationChange: setRoutesPagination,
    state: { pagination: routesPagination },
    autoResetPageIndex: false,
    getRowId: (row) => row.key,
  })

  // Helper function to check if there are actual changes
  const hasActualChanges = (status: any) => {
    if (!status) return false

    const hasDnsChanges = status.dns_diff && (
      (status.dns_diff.records_to_add?.length > 0) ||
      (status.dns_diff.records_to_update?.length > 0) ||
      (status.dns_diff.records_to_remove?.length > 0)
    )

    const hasRouterChanges = status.router_diff && (
      (Object.keys(status.router_diff.routes_to_add || {}).length > 0) ||
      (Object.keys(status.router_diff.routes_to_update || {}).length > 0) ||
      (Object.keys(status.router_diff.routes_to_remove || {}).length > 0)
    )

    return hasDnsChanges || hasRouterChanges
  }

  // Status indicator
  const renderStatusIndicator = () => {
    if (statusLoading || enabledLoading) {
      return (
        <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          检查中...
        </Badge>
      )
    }

    if (statusError) {
      return (
        <Badge variant="destructive">
          <XCircle className="mr-1 h-3 w-3" />
          状态获取失败
        </Badge>
      )
    }

    if (!dnsEnabled?.enabled) {
      return (
        <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">
          <XCircle className="mr-1 h-3 w-3" />
          DNS管理未启用
        </Badge>
      )
    }

    if (!dnsStatus?.initialized) {
      return (
        <Badge className="bg-orange-100 text-orange-800 hover:bg-orange-100">
          <AlertCircle className="mr-1 h-3 w-3" />
          DNS管理器未初始化
        </Badge>
      )
    }

    if (hasActualChanges(dnsStatus)) {
      return (
        <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">
          <AlertCircle className="mr-1 h-3 w-3" />
          有待同步的变更
        </Badge>
      )
    }

    return (
      <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
        <CheckCircle2 className="mr-1 h-3 w-3" />
        状态正常
      </Badge>
    )
  }

  // Render errors
  const renderErrors = () => {
    if (!statusError) return null

    let errorMessage = '未知错误'
    if (statusError && typeof statusError === 'object' && 'response' in statusError) {
      const axiosError = statusError as any
      errorMessage = axiosError.response?.data?.detail || axiosError.message || '未知错误'
    } else if (statusError instanceof Error) {
      errorMessage = statusError.message || '未知错误'
    }

    return (
      <Alert variant="destructive">
        <AlertTitle>状态检查错误</AlertTitle>
        <AlertDescription>{errorMessage}</AlertDescription>
      </Alert>
    )
  }

  // Render differences
  const renderDifferences = () => {
    if (!dnsStatus || !hasActualChanges(dnsStatus)) return null

    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>检测到待同步的变更</AlertTitle>
        <AlertDescription>
          <div className="space-y-4 mt-2">
            {dnsStatus.dns_diff && (
              dnsStatus.dns_diff.records_to_add?.length > 0 ||
              dnsStatus.dns_diff.records_to_update?.length > 0 ||
              dnsStatus.dns_diff.records_to_remove?.length > 0
            ) && (
              <div>
                <p className="font-medium">DNS记录变更:</p>
                <div className="ml-4 mt-2 space-y-2">
                  {dnsStatus.dns_diff.records_to_add?.length > 0 && (
                    <div>
                      <p className="text-green-600 font-medium">新增记录 ({dnsStatus.dns_diff.records_to_add.length} 条):</p>
                      <ul className="ml-4 mt-1">
                        {dnsStatus.dns_diff.records_to_add.map((record: any, index: number) => (
                          <li key={index} className="text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{record.sub_domain}</code>
                            {' → '}
                            <span className="text-green-600">{record.record_type}</span>
                            {' → '}
                            <span>{record.value}</span> (TTL: {record.ttl}s)
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {dnsStatus.dns_diff.records_to_update?.length > 0 && (
                    <div>
                      <p className="text-yellow-600 font-medium">更新记录 ({dnsStatus.dns_diff.records_to_update.length} 条):</p>
                      <ul className="ml-4 mt-1">
                        {dnsStatus.dns_diff.records_to_update.map((record: any, index: number) => (
                          <li key={index} className="text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{record.sub_domain}</code>
                            {' → '}
                            <span className="text-yellow-600">{record.record_type}</span>
                            {' → '}
                            <span>{record.value}</span> (TTL: {record.ttl}s)
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {dnsStatus.dns_diff.records_to_remove?.length > 0 && (
                    <div>
                      <p className="text-red-600 font-medium">删除记录 ({dnsStatus.dns_diff.records_to_remove.length} 条):</p>
                      <ul className="ml-4 mt-1">
                        {dnsStatus.dns_diff.records_to_remove.map((recordId: string, index: number) => (
                          <li key={index} className="text-sm text-red-600">
                            记录ID: {recordId}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
            {dnsStatus.router_diff && (
              Object.keys(dnsStatus.router_diff.routes_to_add || {}).length > 0 ||
              Object.keys(dnsStatus.router_diff.routes_to_update || {}).length > 0 ||
              Object.keys(dnsStatus.router_diff.routes_to_remove || {}).length > 0
            ) && (
              <div>
                <p className="font-medium">路由变更:</p>
                <div className="ml-4 mt-2 space-y-2">
                  {Object.keys(dnsStatus.router_diff.routes_to_add || {}).length > 0 && (
                    <div>
                      <p className="text-green-600 font-medium">新增路由 ({Object.keys(dnsStatus.router_diff.routes_to_add).length} 条):</p>
                      <ul className="ml-4 mt-1">
                        {Object.entries(dnsStatus.router_diff.routes_to_add).map(([serverAddress, backend], index) => (
                          <li key={index} className="text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{serverAddress}</code>
                            {' → '}
                            <span className="text-green-600">{String(backend)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {Object.keys(dnsStatus.router_diff.routes_to_update || {}).length > 0 && (
                    <div>
                      <p className="text-yellow-600 font-medium">更新路由 ({Object.keys(dnsStatus.router_diff.routes_to_update).length} 条):</p>
                      <ul className="ml-4 mt-1">
                        {Object.entries(dnsStatus.router_diff.routes_to_update).map(([serverAddress, changes], index) => (
                          <li key={index} className="text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{serverAddress}</code>
                            {' → '}
                            <span className="text-yellow-600">{JSON.stringify(changes)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {Object.keys(dnsStatus.router_diff.routes_to_remove || {}).length > 0 && (
                    <div>
                      <p className="text-red-600 font-medium">删除路由 ({Object.keys(dnsStatus.router_diff.routes_to_remove).length} 条):</p>
                      <ul className="ml-4 mt-1">
                        {Object.entries(dnsStatus.router_diff.routes_to_remove).map(([serverAddress, backend], index) => (
                          <li key={index} className="text-sm">
                            <code className="bg-muted px-1 py-0.5 rounded text-xs">{serverAddress}</code>
                            {' → '}
                            <span className="text-red-600">{String(backend)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </AlertDescription>
      </Alert>
    )
  }

  const renderTable = (table: ReturnType<typeof useReactTable<any>>) => (
    <DataTable table={table} pageSizeOptions={[10, 20, 50]} />
  )

  return (
    <div className="space-y-4">
      <PageHeader
        title="DNS管理"
        icon={<Globe className="h-5 w-5" />}
        actions={
          <>
            {renderStatusIndicator()}
            <Button
              variant="outline"
              onClick={handleRefresh}
              disabled={refreshDataMutation.isPending}
              title="重新获取DNS记录和路由信息"
            >
              {refreshDataMutation.isPending
                ? <Spinner className="mr-2 size-4" />
                : <RotateCw className="mr-2 h-4 w-4" />
              }
              刷新
            </Button>
            <Button
              onClick={handleUpdate}
              disabled={updateDNSMutation.isPending || !dnsEnabled?.enabled}
              title="手动触发DNS和路由更新"
            >
              {updateDNSMutation.isPending
                ? <Spinner className="mr-2 size-4" />
                : <RefreshCw className="mr-2 h-4 w-4" />
              }
              更新记录
            </Button>
            <Button
              variant="outline"
              onClick={handleGoToSettings}
              title="跳转到DNS配置页面"
            >
              <Settings className="mr-2 h-4 w-4" />
              转到设置
            </Button>
          </>
        }
      />

      {renderErrors()}
      {renderDifferences()}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* DNS Records */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Globe className="h-4 w-4" />
                <span>DNS记录</span>
                {dnsRecords && (
                  <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">
                    {dnsRecords.length} 条记录
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {recordsLoading ? (
                <LoadingSpinner height="8rem" />
              ) : !isDNSEnabled ? (
                <Alert>
                  <AlertTitle>DNS管理未启用</AlertTitle>
                  <AlertDescription className="flex items-center justify-between">
                    <span>请前往设置页面启用DNS管理功能</span>
                    <Button size="sm" onClick={handleGoToSettings}>
                      前往设置
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : recordsError ? (
                <Alert variant="destructive">
                  <AlertTitle>DNS记录加载失败</AlertTitle>
                  <AlertDescription>{String(recordsError)}</AlertDescription>
                </Alert>
              ) : (
                renderTable(dnsTable)
              )}
            </CardContent>
          </Card>
        </div>

        {/* Router Routes */}
        <div>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Share2 className="h-4 w-4" />
                <span>MC Router路由</span>
                {routerRoutes && (
                  <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
                    {Object.keys(routerRoutes).length} 条路由
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {routesLoading ? (
                <LoadingSpinner height="8rem" />
              ) : !isDNSEnabled ? (
                <Alert>
                  <AlertTitle>DNS管理未启用</AlertTitle>
                  <AlertDescription className="flex items-center justify-between">
                    <span>请前往设置页面启用DNS管理功能</span>
                    <Button size="sm" onClick={handleGoToSettings}>
                      前往设置
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : routesError ? (
                <Alert variant="destructive">
                  <AlertTitle>路由信息加载失败</AlertTitle>
                  <AlertDescription>{String(routesError)}</AlertDescription>
                </Alert>
              ) : (
                renderTable(routesTable)
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default DnsManagement
