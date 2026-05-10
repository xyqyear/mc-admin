import React from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import type { ServerStatus } from '@/types/ServerInfo'

interface ServerStopGuardProps {
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

// Backend re-checks inside the lock (409); the banner is a pre-flight UX nudge.
const isStopped = (status: ServerStatus | undefined): boolean =>
  status === 'EXISTS' || status === 'CREATED' || status === 'REMOVED'

export const ServerStopGuard: React.FC<ServerStopGuardProps> = ({
  status,
}) => {
  if (!status) return null
  if (isStopped(status)) return null

  return (
    <Alert variant="destructive">
      <AlertTitle>服务器运行中，无法恢复</AlertTitle>
      <AlertDescription>
        状态：{STATUS_LABEL[status]}。世界恢复需要先停止服务器，避免在恢复过程中产生写入冲突。
      </AlertDescription>
    </Alert>
  )
}

export default ServerStopGuard
