import React, { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Progress } from '@/shared/ui/progress'
import type { InitEvent } from '@/features/world/map/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { worldApi } from '@/features/world/api'
import { taskApi } from '@/features/tasks/api'
import type { TaskAccepted } from '@/features/tasks/contracts'
import { waitForTaskResult } from '@/features/tasks/commands'

interface MapInitDialogProps {
  open: boolean
  serverId: string
  force?: boolean
  onClose: () => void
  onComplete: () => void
}

interface StageState {
  percent: number
  message: string
  done: boolean
  cached: boolean
}

const initialStage: StageState = {
  percent: 0,
  message: '准备中...',
  done: false,
  cached: false,
}

const MapInitDialog: React.FC<MapInitDialogProps> = ({
  open,
  serverId,
  force = false,
  onClose,
  onComplete,
}) => {
  const queryClient = useQueryClient()
  const request = useRef<{ key: string; accepted: Promise<TaskAccepted> } | null>(null)
  const [isActive, setIsActive] = useState(true)
  const [client, setClient] = useState<StageState>(initialStage)
  const [palette, setPalette] = useState<StageState>(initialStage)
  const [errored, setErrored] = useState<string | null>(null)

  const applyEvent = (event: InitEvent) => {
    if (event.stage === 'client') {
      setClient((prev) => ({
        percent: event.percent ?? prev.percent,
        message: event.message ?? prev.message,
        done: event.phase === 'done',
        cached: event.cached ?? prev.cached,
      }))
    } else if (event.stage === 'palette') {
      setPalette((prev) => ({
        percent: event.percent ?? prev.percent,
        message: event.message ?? prev.message,
        done: event.phase === 'done',
        cached: event.cached ?? prev.cached,
      }))
    }
  }

  useEffect(() => {
    if (!open) { request.current = null; return }
    setClient(initialStage)
    setPalette(initialStage)
    setErrored(null)
    setIsActive(true)
    const ctrl = new AbortController()
    const key = `${serverId}:${force}`
    if (request.current?.key !== key) {
      request.current = {
        key,
        accepted: taskApi.getActiveTasks().then(tasks => {
          const active = tasks.find(task => task.taskType === 'map_initialize' && task.serverId === serverId)
          return active ? { task_id: active.taskId } : worldApi.initializeMap(serverId, force)
        }),
      }
    }
    void request.current.accepted.then(accepted => waitForTaskResult(queryClient, accepted, {
      signal: ctrl.signal,
      onProgress: task => {
        const result = task.result as { stages?: Record<string, InitEvent> } | undefined
        Object.values(result?.stages ?? {}).forEach(applyEvent)
      },
    })).then(() => {
      if (ctrl.signal.aborted) return
      setIsActive(false)
      toast.success('地图初始化完成')
      onComplete()
    }).catch((error: Error) => {
      if (ctrl.signal.aborted) return
      setIsActive(false)
      setErrored(error.message)
    })
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, serverId, force, queryClient])

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !isActive && onClose()}>
      <DialogContent showCloseButton={!isActive}>
        <DialogHeader>
          <DialogTitle>
            {force ? '正在重载渲染前置' : '正在初始化地图'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <StageRow
            label="客户端 JAR"
            stage={client}
            doneSuffix={client.cached ? '（已缓存）' : ''}
          />
          <StageRow
            label="调色板"
            stage={palette}
            doneSuffix={palette.cached ? '（已缓存）' : ''}
          />
          {errored && (
            <div className="text-destructive text-sm">错误: {errored}</div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface StageRowProps {
  label: string
  stage: StageState
  doneSuffix?: string
}

const StageRow: React.FC<StageRowProps> = ({ label, stage, doneSuffix }) => (
  <div>
    <div className="flex justify-between text-sm mb-1">
      <span>{label}</span>
      <span className="text-muted-foreground">
        {stage.done ? `100%${doneSuffix ?? ''}` : `${Math.round(stage.percent)}%`}
      </span>
    </div>
    <Progress value={stage.done ? 100 : stage.percent} />
    <div className="text-muted-foreground text-xs mt-1">{stage.message}</div>
  </div>
)

export default MapInitDialog
