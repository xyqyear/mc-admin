import React, { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import type { InitEvent } from '@/types/MapTypes'
import { readEventStream } from '@/utils/eventStream'

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
    if (!open) return
    setClient(initialStage)
    setPalette(initialStage)
    setErrored(null)

    const ctrl = new AbortController()
    let completed = false

    void readEventStream<InitEvent>({
      url: `/servers/${serverId}/map/initialize${force ? '?force=true' : ''}`,
      method: 'POST',
      signal: ctrl.signal,
      onEvent: (event) => {
        applyEvent(event)
        if (event.stage === 'complete') {
          completed = true
        }
        if (event.phase === 'error') {
          setErrored(event.message ?? '未知错误')
          ctrl.abort()
        }
      },
      onClose: () => {
        if (!completed) return
        toast.success('地图初始化完成')
        onComplete()
      },
      onError: (message) => {
        setErrored(message)
      },
    })

    return () => {
      ctrl.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, serverId, force])

  const isActive = !errored && (!client.done || !palette.done)

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
