import React, { useState } from 'react';
import {
  Card,
  Table,
  Button,
  Tooltip,
  Alert,
  Tag,
  Typography,
  Popconfirm,
  Modal,
  Space,
  type TableProps,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  HistoryOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  UnlockOutlined,
} from '@ant-design/icons';
import PageHeader from '@/components/layout/PageHeader';
import type { Snapshot } from '@/hooks/api/snapshotApi';
import { snapshotApi } from '@/hooks/api/snapshotApi';
import { useSnapshotQueries } from '@/hooks/queries/base/useSnapshotQueries';
import { useSnapshotMutations } from '@/hooks/mutations/useSnapshotMutations';
import { formatDateTime } from '@/utils/formatUtils';

const { Text } = Typography;

const Snapshots: React.FC = () => {
  const { useGlobalSnapshots } = useSnapshotQueries();
  const { useCreateGlobalSnapshot, useDeleteSnapshot, useUnlockRepository } = useSnapshotMutations();

  // 分页状态管理
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);

  // 解锁对话框状态
  const [unlockModalVisible, setUnlockModalVisible] = useState(false);
  const [locksInfo, setLocksInfo] = useState<string>('');
  const [unlockOutput, setUnlockOutput] = useState<string>('');
  const [isLoadingLocks, setIsLoadingLocks] = useState(false);

  const {
    data: snapshots = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useGlobalSnapshots();

  const createSnapshotMutation = useCreateGlobalSnapshot();
  const deleteSnapshotMutation = useDeleteSnapshot();
  const unlockMutation = useUnlockRepository();

  const handleCreateSnapshot = () => {
    createSnapshotMutation.mutate();
  };

  const handleDeleteSnapshot = (snapshotId: string) => {
    deleteSnapshotMutation.mutate(snapshotId);
  };

  const handleUnlockClick = async () => {
    setIsLoadingLocks(true);
    setUnlockOutput('');

    try {
      // 首先获取锁信息
      const locksResult = await snapshotApi.listLocks();
      setLocksInfo(locksResult.locks);
      setUnlockModalVisible(true);
    } catch (error: any) {
      Modal.error({
        title: '获取锁信息失败',
        content: error?.message || '未知错误',
      });
    } finally {
      setIsLoadingLocks(false);
    }
  };

  const handleUnlock = () => {
    unlockMutation.mutate(undefined, {
      onSuccess: (data) => {
        setUnlockOutput(data.output);
        Modal.success({
          title: '解锁成功',
          content: data.message,
        });
      },
    });
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
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_: any, record: Snapshot) => (
        <Popconfirm
          title="删除快照"
          description={
            <div>
              <div>确定要删除此快照吗？</div>
              <div className="text-xs text-gray-500 mt-1">
                快照ID: {record.short_id}
              </div>
            </div>
          }
          onConfirm={() => handleDeleteSnapshot(record.id)}
          okText="确认删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
        >
          <Button
            danger
            size="small"
            icon={<DeleteOutlined />}
            loading={deleteSnapshotMutation.isPending}
          >
            删除
          </Button>
        </Popconfirm>
      ),
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
              danger
              icon={<UnlockOutlined />}
              onClick={handleUnlockClick}
              loading={isLoadingLocks}
            >
              解锁仓库
            </Button>
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
          size="small"
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
                  点击&quot;创建全局快照&quot;开始备份服务器数据
                </div>
              </div>
            ),
          }}
        />
      </Card>

      {/* 解锁仓库对话框 */}
      <Modal
        title="解锁 Restic 仓库"
        open={unlockModalVisible}
        onCancel={() => setUnlockModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setUnlockModalVisible(false)}>
            取消
          </Button>,
          <Popconfirm
            key="unlock"
            title="确认解锁"
            description="确定要解锁 Restic 仓库吗？这将移除所有陈旧的锁。"
            onConfirm={handleUnlock}
            okText="确认解锁"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              danger
              type="primary"
              loading={unlockMutation.isPending}
              disabled={unlockOutput !== ''}
            >
              解锁
            </Button>
          </Popconfirm>,
        ]}
        width={700}
      >
        <Space direction="vertical" className="w-full" size="large">
          <div>
            <Text strong>当前锁信息：</Text>
            <pre className="mt-2 p-3 bg-gray-100 rounded border border-gray-300 overflow-auto max-h-60">
              {locksInfo || '无锁信息'}
            </pre>
          </div>

          {unlockOutput && (
            <div>
              <Text strong className="text-green-600">解锁输出：</Text>
              <pre className="mt-2 p-3 bg-green-50 rounded border border-green-300 overflow-auto max-h-60">
                {unlockOutput}
              </pre>
            </div>
          )}
        </Space>
      </Modal>
    </div>
  );
};

export default Snapshots;