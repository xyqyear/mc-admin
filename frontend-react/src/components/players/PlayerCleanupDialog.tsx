import React from 'react'
import { AlertTriangle, Trash2, UserX } from 'lucide-react'
import { toast } from 'sonner'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/common/EmptyState'
import {
  usePlayerCleanupPreview,
} from '@/hooks/queries/base/usePlayerQueries'
import { usePlayerMutations } from '@/hooks/mutations/usePlayerMutations'
import type {
  PlayerCleanupCandidate,
  PlayerCleanupKind,
} from '@/hooks/api/playerApi'
import { formatUUID } from '@/utils/formatUtils'

interface PlayerCleanupDialogProps {
  kind: PlayerCleanupKind | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const cleanupCopy = {
  offline_uuid: {
    title: '清理离线 UUID 玩家',
    description: '这些玩家的 UUID 不符合在线模式记录规则。',
    confirmText: '删除离线 UUID 玩家',
    emptyTitle: '没有离线 UUID 玩家',
    emptyDescription: '当前玩家数据库中没有需要清理的离线 UUID 记录。',
  },
  ignored_name_prefix: {
    title: '清理忽略前缀玩家',
    description: '这些玩家名匹配当前忽略前缀配置。',
    confirmText: '删除忽略前缀玩家',
    emptyTitle: '没有忽略前缀玩家',
    emptyDescription: '当前玩家数据库中没有匹配忽略前缀的记录。',
  },
} satisfies Record<PlayerCleanupKind, {
  title: string
  description: string
  confirmText: string
  emptyTitle: string
  emptyDescription: string
}>

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleString('zh-CN') : '-'

const getRelatedCount = (player: PlayerCleanupCandidate) =>
  player.session_count + player.chat_message_count + player.achievement_count

const PlayerCleanupDialog: React.FC<PlayerCleanupDialogProps> = ({
  kind,
  open,
  onOpenChange,
}) => {
  const copy = kind ? cleanupCopy[kind] : cleanupCopy.offline_uuid
  const previewQuery = usePlayerCleanupPreview(kind, open)
  const { useDeletePlayerCleanup } = usePlayerMutations()
  const deleteCleanupMutation = useDeletePlayerCleanup()

  const candidates = previewQuery.data?.candidates ?? []
  const activePrefixes = previewQuery.data?.ignored_name_prefixes ?? []

  const handleDelete = async () => {
    if (!kind) return

    try {
      const result = await deleteCleanupMutation.mutateAsync(kind)
      toast.success(`已删除 ${result.deleted_count} 个玩家`)
      onOpenChange(false)
    } catch (error: any) {
      toast.error(`清理失败: ${error.message || '未知错误'}`)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !deleteCleanupMutation.isPending) onOpenChange(false)
      }}
    >
      <DialogContent className="sm:max-w-250 max-h-[85vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserX />
            <span>{copy.title}</span>
            <Badge variant="secondary">{candidates.length} 个玩家</Badge>
          </DialogTitle>
          <DialogDescription>
            <span>{copy.description}</span>
            {kind === 'ignored_name_prefix' && (
              <span className="mt-2 flex flex-wrap gap-1.5">
                {activePrefixes.length > 0 ? (
                  activePrefixes.map((prefix) => (
                    <Badge key={prefix} variant="outline">
                      {prefix}
                    </Badge>
                  ))
                ) : (
                  <Badge variant="outline">无前缀</Badge>
                )}
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-col gap-3">
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>删除后无法恢复</AlertTitle>
            <AlertDescription>
              玩家记录、会话、聊天和成就数据会一起删除。
            </AlertDescription>
          </Alert>

          {previewQuery.isLoading || previewQuery.isFetching ? (
            <div className="flex items-center justify-center py-16">
              <Spinner className="size-8" />
            </div>
          ) : previewQuery.error ? (
            <Alert variant="destructive">
              <AlertTitle>加载清理预览失败</AlertTitle>
              <AlertDescription>
                {previewQuery.error.message || '发生未知错误'}
              </AlertDescription>
            </Alert>
          ) : candidates.length === 0 ? (
            <div className="rounded-md border py-12">
              <EmptyState
                title={copy.emptyTitle}
                description={copy.emptyDescription}
              />
            </div>
          ) : (
            <ScrollArea className="h-[50vh] rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>玩家</TableHead>
                    <TableHead>首次加入</TableHead>
                    <TableHead>最后在线</TableHead>
                    <TableHead>关联记录</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {candidates.map((player) => (
                    <TableRow key={player.player_db_id}>
                      <TableCell>
                        <div className="flex min-w-0 flex-col gap-1">
                          <span className="font-medium">{player.current_name}</span>
                          <span
                            className="truncate text-xs text-muted-foreground"
                            title={formatUUID(player.uuid)}
                          >
                            UUID: {formatUUID(player.uuid)}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>{formatDate(player.first_seen)}</TableCell>
                      <TableCell>{formatDate(player.last_seen)}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          <Badge variant="secondary">
                            会话 {player.session_count}
                          </Badge>
                          <Badge variant="secondary">
                            聊天 {player.chat_message_count}
                          </Badge>
                          <Badge variant="secondary">
                            成就 {player.achievement_count}
                          </Badge>
                          <Badge variant="outline">
                            共 {getRelatedCount(player)}
                          </Badge>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={deleteCleanupMutation.isPending}
          >
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={
              deleteCleanupMutation.isPending ||
              previewQuery.isLoading ||
              candidates.length === 0
            }
          >
            {deleteCleanupMutation.isPending ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <Trash2 data-icon="inline-start" />
            )}
            {copy.confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default PlayerCleanupDialog
