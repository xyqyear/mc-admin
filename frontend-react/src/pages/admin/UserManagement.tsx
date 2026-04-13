import React, { useState, useMemo } from 'react'
import {
  Crown,
  Plus,
  Trash2,
  User,
  Users,
} from 'lucide-react'
import {
  type ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useForm, Controller } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import PageHeader from '@/components/layout/PageHeader'
import { DataTable } from '@/components/common/DataTable'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useConfirm } from '@/hooks/useConfirm'
import { useAllUsers } from '@/hooks/queries/base/useUserQueries'
import { useCreateUser, useDeleteUser } from '@/hooks/mutations/useUserMutations'
import { UserRole, type UserCreate, type User as UserType } from '@/types/User'

const createUserSchema = z.object({
  username: z
    .string()
    .min(3, '用户名至少需要3个字符')
    .max(50, '用户名不能超过50个字符'),
  password: z
    .string()
    .min(6, '密码至少需要6个字符'),
  role: z.enum([UserRole.ADMIN, UserRole.OWNER]),
})

type CreateUserForm = z.infer<typeof createUserSchema>

const staticColumns: ColumnDef<UserType, any>[] = [
  {
    accessorKey: 'username',
    header: '用户名',
    cell: ({ row }) => (
      <div className="flex items-center gap-2">
        {row.original.role === UserRole.OWNER ? (
          <Crown className="h-4 w-4 text-yellow-500" />
        ) : (
          <User className="h-4 w-4" />
        )}
        <span>{row.original.username}</span>
      </div>
    ),
  },
  {
    accessorKey: 'role',
    header: '权限',
    cell: ({ row }) => {
      const role = row.original.role
      return role === UserRole.OWNER ? (
        <StatusBadge tone="warning" badgeStyle="soft">超级管理员</StatusBadge>
      ) : (
        <StatusBadge tone="info" badgeStyle="soft">管理员</StatusBadge>
      )
    },
  },
  {
    accessorKey: 'created_at',
    header: '注册日期',
    cell: ({ row }) => new Date(row.original.created_at).toLocaleString('zh-CN'),
  },
]

const UserManagement: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)

  const { confirm, confirmDialog } = useConfirm()

  const usersQuery = useAllUsers()
  const users = usersQuery.data || []

  const createUserMutation = useCreateUser()
  const deleteUserMutation = useDeleteUser()

  const {
    control,
    handleSubmit,
    reset,
  } = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      username: '',
      password: '',
      role: UserRole.ADMIN,
    },
  })

  const actionColumn: ColumnDef<UserType, any> = useMemo(() => ({
    id: 'actions',
    header: '操作',
    cell: ({ row }) => (
      <Button
        variant="ghost"
        size="sm"
        className="text-destructive hover:text-destructive"
        onClick={() =>
          confirm({
            title: '删除用户',
            description: `确定要删除用户 "${row.original.username}" 吗？`,
            confirmText: '确定',
            cancelText: '取消',
            variant: 'destructive',
            onConfirm: async () => { await deleteUserMutation.mutateAsync(row.original.id) },
          })
        }
      >
        <Trash2 className="mr-1 h-3.5 w-3.5" />
        删除
      </Button>
    ),
  }), [confirm, deleteUserMutation])

  const allColumns = useMemo(() => [...staticColumns, actionColumn], [actionColumn])

  const table = useReactTable({
    data: users,
    columns: allColumns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId: (row) => String(row.id),
    autoResetPageIndex: false,
    initialState: { pagination: { pageSize: 10 } },
  })

  const showCreateModal = () => {
    reset({ username: '', password: '', role: UserRole.ADMIN })
    setIsCreateModalOpen(true)
  }

  const handleCreateSubmit = handleSubmit(async (values: CreateUserForm) => {
    await createUserMutation.mutateAsync(values as UserCreate)
    setIsCreateModalOpen(false)
    reset()
  })

  if (usersQuery.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>加载用户数据失败</AlertTitle>
        <AlertDescription className="flex items-center justify-between">
          <span>{usersQuery.error?.message || '请检查网络连接或稍后重试'}</span>
          <Button size="sm" variant="outline" onClick={() => usersQuery.refetch()}>
            重试
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="用户管理"
        icon={<User />}
        actions={
          <Button onClick={showCreateModal}>
            <Plus className="mr-1 h-4 w-4" />
            新建用户
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              <CardTitle className="text-base">用户列表</CardTitle>
              <span className="text-sm text-muted-foreground font-normal">
                ({users.length} 个用户)
              </span>
            </div>
            <CardDescription>
              管理系统用户账户和权限
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <DataTable
            table={table}
            rowLabel="个用户"
            emptyMessage="暂无用户数据"
          />
        </CardContent>
      </Card>

      {/* Create user dialog */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>新建用户</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateSubmit} className="space-y-4">
            <Controller
              name="username"
              control={control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor={field.name}>用户名</FieldLabel>
                  <Input
                    {...field}
                    id={field.name}
                    placeholder="请输入用户名"
                    aria-invalid={fieldState.invalid}
                  />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />

            <Controller
              name="password"
              control={control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor={field.name}>密码</FieldLabel>
                  <Input
                    {...field}
                    id={field.name}
                    type="password"
                    placeholder="请输入密码"
                    aria-invalid={fieldState.invalid}
                  />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />

            <Controller
              name="role"
              control={control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel>角色</FieldLabel>
                  <Select
                    value={field.value}
                    onValueChange={(v) => v && field.onChange(v)}
                    itemToStringLabel={(v) =>
                      v === UserRole.OWNER ? '超级管理员' : '管理员'
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="请选择角色" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={UserRole.ADMIN}>
                        <div className="flex items-center gap-2">
                          <User className="h-4 w-4" />
                          管理员
                        </div>
                      </SelectItem>
                      <SelectItem value={UserRole.OWNER}>
                        <div className="flex items-center gap-2">
                          <Crown className="h-4 w-4 text-yellow-500" />
                          超级管理员
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsCreateModalOpen(false)}
              >
                取消
              </Button>
              <Button type="submit" disabled={createUserMutation.isPending}>
                创建
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {confirmDialog}
    </div>
  )
}

export default UserManagement
