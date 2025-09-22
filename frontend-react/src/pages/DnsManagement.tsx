import React from 'react'
import {
  Card,
  Table,
  Button,
  Alert,
  Tag,
  Space,
  Typography,
  Row,
  Col,
  Tooltip,
  App
} from 'antd'
import {
  ReloadOutlined,
  SyncOutlined,
  SettingOutlined,
  GlobalOutlined,
  ShareAltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import { useDNSStatus, useDNSEnabled, useDNSRecords, useRouterRoutes } from '@/hooks/queries/base/useDnsQueries'
import { useUpdateDNS, useRefreshDNSData } from '@/hooks/mutations/useDnsMutations'
import type { DNSRecord } from '@/types/Dns'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

const DnsManagement: React.FC = () => {
  const navigate = useNavigate()
  const { message } = App.useApp()

  // Queries
  const { data: dnsStatus, isLoading: statusLoading, error: statusError } = useDNSStatus()
  const { data: dnsEnabled, isLoading: enabledLoading } = useDNSEnabled()

  // Only fetch DNS records and routes if DNS is enabled
  const isDNSEnabled = dnsEnabled?.enabled ?? false
  const { data: dnsRecords, isLoading: recordsLoading, error: recordsError } = useDNSRecords(isDNSEnabled)
  const { data: routerRoutes, isLoading: routesLoading, error: routesError } = useRouterRoutes(isDNSEnabled)

  // Mutations
  const updateDNSMutation = useUpdateDNS()
  const refreshDataMutation = useRefreshDNSData()

  // Handle refresh data
  const handleRefresh = () => {
    refreshDataMutation.mutate()
  }

  // Handle DNS update
  const handleUpdate = () => {
    if (!dnsEnabled?.enabled) {
      message.warning('DNS管理器未启用，无法执行更新操作')
      return
    }
    updateDNSMutation.mutate()
  }

  // Navigate to dynamic config with dns module selected
  const handleGoToSettings = () => {
    navigate('/config?module=dns')
  }

  // DNS Records table columns
  const dnsRecordsColumns: ColumnsType<DNSRecord> = [
    {
      title: '子域名',
      dataIndex: 'sub_domain',
      key: 'sub_domain',
      width: 200,
    },
    {
      title: '记录类型',
      dataIndex: 'record_type',
      key: 'record_type',
      width: 100,
      render: (type: string) => (
        <Tag color={type === 'A' ? 'blue' : type === 'AAAA' ? 'green' : type === 'SRV' ? 'orange' : 'default'}>
          {type}
        </Tag>
      ),
    },
    {
      title: '值',
      dataIndex: 'value',
      key: 'value',
      ellipsis: true,
    },
    {
      title: 'TTL',
      dataIndex: 'ttl',
      key: 'ttl',
      width: 80,
      render: (ttl: number) => `${ttl}s`,
    },
    {
      title: '记录ID',
      dataIndex: 'record_id',
      key: 'record_id',
      width: 120,
      ellipsis: true,
      render: (id: string | number) => (
        <Text type="secondary" style={{ fontSize: '12px' }}>
          {String(id)}
        </Text>
      ),
    },
  ]

  // Router Routes table columns
  const routerRoutesColumns: ColumnsType<{ server_address: string; backend: string }> = [
    {
      title: '服务器地址',
      dataIndex: 'server_address',
      key: 'server_address',
      ellipsis: true,
    },
    {
      title: '后端地址',
      dataIndex: 'backend',
      key: 'backend',
      width: 150,
    },
  ]

  // Convert router routes to table data
  const routerRoutesData = React.useMemo(() => {
    if (!routerRoutes) return []
    return Object.entries(routerRoutes).map(([server_address, backend]) => ({
      key: server_address,
      server_address,
      backend,
    }))
  }, [routerRoutes])

  // Helper function to check if there are actual changes
  const hasActualChanges = (dnsStatus: any) => {
    if (!dnsStatus) return false

    const hasDnsChanges = dnsStatus.dns_diff && (
      (dnsStatus.dns_diff.records_to_add?.length > 0) ||
      (dnsStatus.dns_diff.records_to_update?.length > 0) ||
      (dnsStatus.dns_diff.records_to_remove?.length > 0)
    )

    const hasRouterChanges = dnsStatus.router_diff && (
      (Object.keys(dnsStatus.router_diff.routes_to_add || {}).length > 0) ||
      (Object.keys(dnsStatus.router_diff.routes_to_update || {}).length > 0) ||
      (Object.keys(dnsStatus.router_diff.routes_to_remove || {}).length > 0)
    )

    return hasDnsChanges || hasRouterChanges
  }

  // Status indicators
  const renderStatusIndicator = () => {
    if (statusLoading || enabledLoading) {
      return <Tag icon={<SyncOutlined spin />} color="processing">检查中...</Tag>
    }

    if (statusError) {
      return <Tag icon={<CloseCircleOutlined />} color="error">状态获取失败</Tag>
    }

    if (!dnsEnabled?.enabled) {
      return <Tag icon={<CloseCircleOutlined />} color="warning">DNS管理未启用</Tag>
    }

    if (!dnsStatus?.initialized) {
      return <Tag icon={<ExclamationCircleOutlined />} color="orange">DNS管理器未初始化</Tag>
    }

    if (hasActualChanges(dnsStatus)) {
      return <Tag icon={<ExclamationCircleOutlined />} color="warning">有待同步的变更</Tag>
    }

    return <Tag icon={<CheckCircleOutlined />} color="success">状态正常</Tag>
  }

  // Render differences
  const renderDifferences = () => {
    if (!dnsStatus || !hasActualChanges(dnsStatus)) {
      return null
    }

    return (
      <Alert
        message="检测到待同步的变更"
        description={
          <div className="space-y-4">
            {dnsStatus.dns_diff && (
              dnsStatus.dns_diff.records_to_add?.length > 0 ||
              dnsStatus.dns_diff.records_to_update?.length > 0 ||
              dnsStatus.dns_diff.records_to_remove?.length > 0
            ) && (
                <div>
                  <Text strong>DNS记录变更:</Text>
                  <div className="ml-4 mt-2 space-y-2">
                    {dnsStatus.dns_diff.records_to_add?.length > 0 && (
                      <div>
                        <Text type="success" strong>新增记录 ({dnsStatus.dns_diff.records_to_add.length} 条):</Text>
                        <ul className="ml-4 mt-1">
                          {dnsStatus.dns_diff.records_to_add.map((record: any, index: number) => (
                            <li key={index} className="text-sm">
                              <Text code>{record.sub_domain}</Text> → <Text type="success">{record.record_type}</Text> → <Text>{record.value}</Text> (TTL: {record.ttl}s)
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {dnsStatus.dns_diff.records_to_update?.length > 0 && (
                      <div>
                        <Text type="warning" strong>更新记录 ({dnsStatus.dns_diff.records_to_update.length} 条):</Text>
                        <ul className="ml-4 mt-1">
                          {dnsStatus.dns_diff.records_to_update.map((record: any, index: number) => (
                            <li key={index} className="text-sm">
                              <Text code>{record.sub_domain}</Text> → <Text type="warning">{record.record_type}</Text> → <Text>{record.value}</Text> (TTL: {record.ttl}s)
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {dnsStatus.dns_diff.records_to_remove?.length > 0 && (
                      <div>
                        <Text type="danger" strong>删除记录 ({dnsStatus.dns_diff.records_to_remove.length} 条):</Text>
                        <ul className="ml-4 mt-1">
                          {dnsStatus.dns_diff.records_to_remove.map((recordId: string, index: number) => (
                            <li key={index} className="text-sm">
                              <Text type="danger">记录ID: {recordId}</Text>
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
                  <Text strong>路由变更:</Text>
                  <div className="ml-4 mt-2 space-y-2">
                    {Object.keys(dnsStatus.router_diff.routes_to_add || {}).length > 0 && (
                      <div>
                        <Text type="success" strong>新增路由 ({Object.keys(dnsStatus.router_diff.routes_to_add).length} 条):</Text>
                        <ul className="ml-4 mt-1">
                          {Object.entries(dnsStatus.router_diff.routes_to_add).map(([serverAddress, backend], index) => (
                            <li key={index} className="text-sm">
                              <Text code>{serverAddress}</Text> → <Text type="success">{String(backend)}</Text>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {Object.keys(dnsStatus.router_diff.routes_to_update || {}).length > 0 && (
                      <div>
                        <Text type="warning" strong>更新路由 ({Object.keys(dnsStatus.router_diff.routes_to_update).length} 条):</Text>
                        <ul className="ml-4 mt-1">
                          {Object.entries(dnsStatus.router_diff.routes_to_update).map(([serverAddress, changes], index) => (
                            <li key={index} className="text-sm">
                              <Text code>{serverAddress}</Text> → <Text type="warning">{JSON.stringify(changes)}</Text>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {Object.keys(dnsStatus.router_diff.routes_to_remove || {}).length > 0 && (
                      <div>
                        <Text type="danger" strong>删除路由 ({Object.keys(dnsStatus.router_diff.routes_to_remove).length} 条):</Text>
                        <ul className="ml-4 mt-1">
                          {Object.entries(dnsStatus.router_diff.routes_to_remove).map(([serverAddress, backend], index) => (
                            <li key={index} className="text-sm">
                              <Text code>{serverAddress}</Text> → <Text type="danger">{String(backend)}</Text>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}
          </div>
        }
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
      />
    )
  }

  // Render errors
  const renderErrors = () => {
    if (!dnsStatus?.errors || dnsStatus.errors.length === 0) {
      return null
    }

    return (
      <Alert
        message="状态检查错误"
        description={
          <ul className="ml-4">
            {dnsStatus.errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        }
        type="error"
        showIcon
        style={{ marginBottom: 16 }}
      />
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader
        title="DNS管理"
        icon={<GlobalOutlined />}
        actions={
          <Space>
            {renderStatusIndicator()}
            <Tooltip title="重新获取DNS记录和路由信息">
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRefresh}
                loading={refreshDataMutation.isPending}
              >
                刷新
              </Button>
            </Tooltip>
            <Tooltip title="手动触发DNS和路由更新">
              <Button
                type="primary"
                icon={<SyncOutlined />}
                onClick={handleUpdate}
                loading={updateDNSMutation.isPending}
                disabled={!dnsEnabled?.enabled}
              >
                更新记录
              </Button>
            </Tooltip>
            <Tooltip title="跳转到DNS配置页面">
              <Button
                icon={<SettingOutlined />}
                onClick={handleGoToSettings}
              >
                转到设置
              </Button>
            </Tooltip>
          </Space>
        }
      />

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {/* Status and differences */}
        <div>
          {renderErrors()}
          {renderDifferences()}
        </div>

        {/* DNS Records and Router Routes */}
        <Row gutter={[16, 16]} style={{ flex: 1, minHeight: 0 }}>
          <Col xs={24} lg={12} style={{ display: 'flex', flexDirection: 'column' }}>
            <Card
              title={
                <Space>
                  <GlobalOutlined />
                  <span>DNS记录</span>
                  {dnsRecords && (
                    <Tag color="blue">{dnsRecords.length} 条记录</Tag>
                  )}
                </Space>
              }
              style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              styles={{ body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } }}
            >
              {recordsLoading ? (
                <LoadingSpinner height="8rem" tip="加载DNS记录中..." />
              ) : !isDNSEnabled ? (
                <Alert
                  message="DNS管理未启用"
                  description="请前往设置页面启用DNS管理功能"
                  type="info"
                  showIcon
                  action={
                    <Button size="small" onClick={handleGoToSettings}>
                      前往设置
                    </Button>
                  }
                />
              ) : recordsError ? (
                <Alert
                  message="DNS记录加载失败"
                  description={String(recordsError)}
                  type="error"
                  showIcon
                />
              ) : (
                <Table
                  columns={dnsRecordsColumns}
                  dataSource={dnsRecords}
                  rowKey="record_id"
                  size="small"
                  pagination={{
                    showSizeChanger: true,
                    showQuickJumper: true,
                    showTotal: (total) => `共 ${total} 条记录`,
                  }}
                  scroll={{ y: 300 }}
                />
              )}
            </Card>
          </Col>

          <Col xs={24} lg={12} style={{ display: 'flex', flexDirection: 'column' }}>
            <Card
              title={
                <Space>
                  <ShareAltOutlined />
                  <span>MC Router路由</span>
                  {routerRoutes && (
                    <Tag color="green">{Object.keys(routerRoutes).length} 条路由</Tag>
                  )}
                </Space>
              }
              style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              styles={{ body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } }}
            >
              {routesLoading ? (
                <LoadingSpinner height="8rem" tip="加载路由信息中..." />
              ) : !isDNSEnabled ? (
                <Alert
                  message="DNS管理未启用"
                  description="请前往设置页面启用DNS管理功能"
                  type="info"
                  showIcon
                  action={
                    <Button size="small" onClick={handleGoToSettings}>
                      前往设置
                    </Button>
                  }
                />
              ) : routesError ? (
                <Alert
                  message="路由信息加载失败"
                  description={String(routesError)}
                  type="error"
                  showIcon
                />
              ) : (
                <Table
                  columns={routerRoutesColumns}
                  dataSource={routerRoutesData}
                  size="small"
                  pagination={{
                    showSizeChanger: true,
                    showQuickJumper: true,
                    showTotal: (total) => `共 ${total} 条路由`,
                  }}
                  scroll={{ y: 300 }}
                />
              )}
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  )
}

export default DnsManagement