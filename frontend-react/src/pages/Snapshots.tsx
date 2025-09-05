import React, { useState } from 'react';
import {
  Card,
  Table,
  Button,
  Tooltip,
  Alert,
  Tag,
  Typography,
  type TableProps,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  HistoryOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import PageHeader from '@/components/layout/PageHeader';
import type { Snapshot } from '@/hooks/api/serverApi';
import { useSnapshotQueries, useSnapshotMutations } from '@/hooks/queries/useSnapshotQueries';

const { Text } = Typography;

const Snapshots: React.FC = () => {
  const { useGlobalSnapshots } = useSnapshotQueries();
  const { useCreateGlobalSnapshot } = useSnapshotMutations();

  // 分页状态管理
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);

  const {
    data: snapshots = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useGlobalSnapshots();

  const createSnapshotMutation = useCreateGlobalSnapshot();

  const handleCreateSnapshot = () => {
    createSnapshotMutation.mutate();
  };

  const formatDateTime = (timeString: string) => {
    return new Date(timeString).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const columns: TableProps<Snapshot>['columns'] = [
    {
      title: '快照ID',
      dataIndex: 'short_id',
      key: 'short_id',
      width: 100,
      render: (shortId: string, record: Snapshot) => (
        <Tooltip title={`完整ID: ${record.id}`}>
          <Tag color="blue" className="font-mono">
            {shortId}
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'time',
      key: 'time',
      width: 180,
      render: (time: string) => (
        <Text className="font-mono text-sm">
          {formatDateTime(time)}
        </Text>
      ),
      sorter: (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: '备份路径',
      dataIndex: 'paths',
      key: 'paths',
      render: (paths: string[]) => (
        <div className="space-y-1">
          {paths.map((path, index) => (
            <Tag key={index} className="font-mono text-xs">
              {path}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: '主机信息',
      key: 'host_info',
      width: 150,
      render: (_: any, record: Snapshot) => (
        <div className="space-y-1">
          <div className="text-sm">
            <Text strong>主机:</Text> {record.hostname}
          </div>
          <div className="text-sm">
            <Text strong>用户:</Text> {record.username}
          </div>
        </div>
      ),
    },
    {
      title: '版本信息',
      dataIndex: 'program_version',
      key: 'program_version',
      width: 120,
      render: (version?: string) => (
        version ? (
          <Tag color="green" className="text-xs">
            {version}
          </Tag>
        ) : (
          <Text type="secondary" className="text-xs">-</Text>
        )
      ),
    },
    {
      title: '统计信息',
      key: 'summary',
      width: 200,
      render: (_: any, record: Snapshot) => {
        if (!record.summary) {
          return <Text type="secondary" className="text-xs">暂无统计</Text>;
        }

        const { summary } = record;
        return (
          <div className="space-y-1 text-xs">
            <div>
              <Text strong>文件:</Text> {summary.total_files_processed} 个
            </div>
            <div>
              <Text strong>数据:</Text> {formatBytes(summary.total_bytes_processed)}
            </div>
            <div>
              <Text strong>新增:</Text> {summary.files_new} 文件 / {summary.dirs_new} 目录
            </div>
            {summary.files_changed > 0 && (
              <div>
                <Text strong>变更:</Text> {summary.files_changed} 个
              </div>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="h-full w-full flex flex-col space-y-4">
      <PageHeader
        title="快照管理"
        icon={<HistoryOutlined />}
        actions={
          <>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => refetch()}
              loading={isLoading}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreateSnapshot}
              loading={createSnapshotMutation.isPending}
            >
              创建全局快照
            </Button>
          </>
        }
      />

      {/* 错误提示 */}
      {isError && (
        <Alert
          message="加载快照列表失败"
          description={(error as any)?.message || '发生未知错误'}
          type="error"
          showIcon
          closable
          action={
            <Button size="small" danger onClick={() => refetch()}>
              重试
            </Button>
          }
        />
      )}

      {/* 快照列表 */}
      <Card
        title={
          <div className="flex items-center space-x-2">
            <CloudServerOutlined />
            <span>快照列表</span>
            <Text type="secondary" className="text-sm font-normal">
              ({snapshots.length} 个快照)
            </Text>
          </div>
        }
        extra={
          <Text type="secondary" className="text-sm">
            显示所有服务器的快照记录
          </Text>
        }
      >
        <Table
          dataSource={snapshots}
          columns={columns}
          rowKey="id"
          scroll={{ x: 'max-content' }}
          loading={isLoading}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total, range) => 
              `${range[0]}-${range[1]} 共 ${total} 个快照`,
            simple: false,
            size: "default",
            onChange: (page, size) => {
              setCurrentPage(page);
              if (size !== pageSize) {
                setPageSize(size);
                setCurrentPage(1); // Reset to first page when page size changes
              }
            },
            onShowSizeChange: (_, size) => {
              setPageSize(size);
              setCurrentPage(1); // Reset to first page when page size changes
            },
          }}
          locale={{
            emptyText: (
              <div className="py-8 text-center">
                <CloudServerOutlined className="text-4xl text-gray-300 mb-2" />
                <div className="text-gray-500">暂无快照数据</div>
                <div className="text-gray-400 text-sm mt-1">
                  点击"创建全局快照"开始备份服务器数据
                </div>
              </div>
            ),
          }}
        />
      </Card>
    </div>
  );
};

export default Snapshots;