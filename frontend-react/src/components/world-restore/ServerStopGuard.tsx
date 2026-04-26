import React from 'react'
import { Play, Square } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useServerOperationConfirm } from '@/components/dialogs/ServerOperationConfirmDialog'
import type { ServerStatus } from '@/types/ServerInfo'
import { serverStatusUtils } from '@/utils/serverUtils'

interface ServerStopGuardProps {
  serverId: string
  status: ServerStatus | undefined
}

const STATUS_LABEL: Record<ServerStatus, string> = {
  REMOVED: '已移除',
  EXISTS: '已停止',
  CREATED: '已创建',
  RUNNING: '运行中',
  STARTING: '启动中',
  HEALTHY: '健康',
}

// Restore is only allowed when the container is *not* up. The backend re-checks
// inside the lock (returns 409), but a pre-flight banner is friendlier and
// gives the user a one-click stop.
const isStopped = (status: ServerStatus | undefined): boolean =>
  status === 'EXISTS' || status === 'CREATED' || status === 'REMOVED'

export const ServerStopGuard: React.FC<ServerStopGuardProps> = ({
  serverId,
  status,
}) => {
  const { useServerOperation } = useServerMutations()
  const op = useServerOperation()
  const { showConfirm, confirmDialog } = useServerOperationConfirm()

  if (!status) return null
  if (isStopped(status)) return null

  const canStop = serverStatusUtils.isOperationAvailable('stop', status)

  return (
    <>
      <Alert variant="destructive">
        <AlertTitle>服务器运行中，无法恢复</AlertTitle>
        <AlertDescription className="flex items-center justify-between gap-3">
          <span>
            状态：{STATUS_LABEL[status]}。世界恢复需要先停止服务器，避免在恢复过程中产生写入冲突。
          </span>
          <Button
            variant="destructive"
            size="sm"
            disabled={op.isPending || !canStop}
            onClick={() =>
              showConfirm({
                operation: 'stop',
                serverName: serverId,
                serverId,
                onConfirm: (action, sid) => op.mutate({ action, serverId: sid }),
              })
            }
          >
            {op.isPending ? (
              <Spinner className="mr-2 size-4" />
            ) : (
              <Square className="mr-2 h-4 w-4" />
            )}
            停止服务器
          </Button>
        </AlertDescription>
      </Alert>
      {confirmDialog}
    </>
  )
}

interface ServerStartHintProps {
  serverId: string
  status: ServerStatus | undefined
}

// Friendlier nudge after a successful restore — tells the user the world is
// back and offers to start the server again. Rendered in the page footer
// area below the map; tolerant of unknown status (returns nothing).
export const ServerStartHint: React.FC<ServerStartHintProps> = ({
  serverId,
  status,
}) => {
  const { useServerOperation } = useServerMutations()
  const op = useServerOperation()

  if (!status) return null
  if (!serverStatusUtils.isOperationAvailable('start', status)) return null

  return (
    <Alert>
      <AlertDescription className="flex items-center justify-between gap-3">
        <span>恢复完成后可以重新启动服务器。</span>
        <Button
          size="sm"
          disabled={op.isPending}
          onClick={() => op.mutate({ action: 'start', serverId })}
        >
          {op.isPending ? (
            <Spinner className="mr-2 size-4" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          启动服务器
        </Button>
      </AlertDescription>
    </Alert>
  )
}

export default ServerStopGuard
