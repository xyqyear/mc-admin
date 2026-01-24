import React, { useState } from 'react'
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Popconfirm,
  Space,
  Alert,
  Tag,
  Typography,
  type TableProps
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  UserOutlined,
  CrownOutlined,
  TeamOutlined
} from '@ant-design/icons'
import PageHeader from '@/components/layout/PageHeader'
import { useAllUsers } from '@/hooks/queries/base/useUserQueries'
import { useCreateUser, useDeleteUser } from '@/hooks/mutations/useUserMutations'
import { UserRole, type User, type UserCreate } from '@/types/User'

const { Text } = Typography

const UserManagement: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [createForm] = Form.useForm()

  // Data fetching
  const usersQuery = useAllUsers()
  const users = usersQuery.data || []

  // Mutations
  const createUserMutation = useCreateUser()
  const deleteUserMutation = useDeleteUser()

  // Modal handlers
  const showCreateModal = () => {
    setIsCreateModalOpen(true)
  }

  const handleCreateCancel = () => {
    setIsCreateModalOpen(false)
    createForm.resetFields()
  }

  const handleCreateSubmit = async () => {
    try {
      const values = await createForm.validateFields()
      await createUserMutation.mutateAsync(values as UserCreate)
      setIsCreateModalOpen(false)
      createForm.resetFields()
    } catch {
      // Error is handled by the mutation
    }
  }

  const handleDeleteUser = async (userId: number) => {
    await deleteUserMutation.mutateAsync(userId)
  }

  // Table columns
  const columns: TableProps<User>['columns'] = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      render: (username: string, record: User) => (
        <Space>
          {record.role === UserRole.OWNER ? (
            <CrownOutlined style={{ color: '#faad14' }} />
          ) : (
            <UserOutlined />
          )}
          {username}
        </Space>
      ),
    },
    {
      title: '权限',
      dataIndex: 'role',
      key: 'role',
      render: (role: UserRole) => (
        <Tag color={role === UserRole.OWNER ? 'gold' : 'blue'}>
          {role === UserRole.OWNER ? '超级管理员' : '管理员'}
        </Tag>
      ),
    },
    {
      title: '注册日期',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) =>
        new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record: User) => (
        <Popconfirm
          title="删除用户"
          description={`确定要删除用户 "${record.username}" 吗？`}
          onConfirm={() => handleDeleteUser(record.id)}
          okText="确定"
          cancelText="取消"
          disabled={deleteUserMutation.isPending}
        >
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            loading={deleteUserMutation.isPending}
            size="small"
          >
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  if (usersQuery.isError) {
    return (
      <Alert
        title="加载用户数据失败"
        description={usersQuery.error?.message || '请检查网络连接或稍后重试'}
        type="error"
        showIcon
        action={
          <Button size="small" onClick={() => usersQuery.refetch()}>
            重试
          </Button>
        }
      />
    )
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="用户管理"
        icon={<UserOutlined />}
        actions={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={showCreateModal}
          >
            新建用户
          </Button>
        }
      />

      <Card
        title={
          <div className="flex items-center space-x-2">
            <TeamOutlined />
            <span>用户列表</span>
            <Text type="secondary" className="text-sm font-normal">
              ({users.length} 个用户)
            </Text>
          </div>
        }
        extra={
          <Text type="secondary" className="text-sm">
            管理系统用户账户和权限
          </Text>
        }
      >
        <Table<User>
          columns={columns}
          dataSource={users}
          rowKey="id"
          loading={usersQuery.isLoading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 个用户`,
          }}
        />
      </Card>

      {/* 新建用户模态框 */}
      <Modal
        title="新建用户"
        open={isCreateModalOpen}
        onOk={handleCreateSubmit}
        onCancel={handleCreateCancel}
        confirmLoading={createUserMutation.isPending}
        okText="创建"
        cancelText="取消"
      >
        <Form
          form={createForm}
          layout="vertical"
          name="createUser"
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少需要3个字符' },
              { max: 50, message: '用户名不能超过50个字符' },
            ]}
          >
            <Input placeholder="请输入用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少需要6个字符' },
            ]}
          >
            <Input.Password placeholder="请输入密码" />
          </Form.Item>

          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
            initialValue={UserRole.ADMIN}
          >
            <Select placeholder="请选择角色">
              <Select.Option value={UserRole.ADMIN}>
                <Space>
                  <UserOutlined />
                  管理员
                </Space>
              </Select.Option>
              <Select.Option value={UserRole.OWNER}>
                <Space>
                  <CrownOutlined style={{ color: '#faad14' }} />
                  超级管理员
                </Space>
              </Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default UserManagement