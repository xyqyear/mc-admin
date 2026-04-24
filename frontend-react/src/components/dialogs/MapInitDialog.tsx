import React, { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import type { InitEvent } from '@/types/MapTypes'
import { getApiBaseUrl } from '@/utils/api'
import { useTokenStore } from '@/stores/useTokenStore'

interface MapInitDialogProps {
  open: boolean
  serverId: string
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
  onClose,
  onComplete,
}) => {
  const [client, setClient] = useState<StageState>(initialStage)
  const [palette, setPalette] = useState<StageState>(initialStage)
  const [errored, setErrored] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!open) return
    setClient(initialStage)
    setPalette(initialStage)
    setErrored(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    ;(async () => {
      try {
        const token = useTokenStore.getState().token
        const res = await fetch(
          `${getApiBaseUrl()}/servers/${serverId}/map/initialize`,
          {
            method: 'POST',
            headers: {
              Authorization: token ? `Bearer ${token}` : '',
              Accept: 'text/event-stream',
            },
            signal: ctrl.signal,
          }
        )
        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let completed = false

        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          let idx: number
          while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const block = buffer.slice(0, idx)
            buffer = buffer.slice(idx + 2)
            const dataLines = block
              .split('\n')
              .filter((l) => l.startsWith('data:'))
              .map((l) => l.slice(5).trim())
            if (dataLines.length === 0) continue
            const payload = dataLines.join('\n')
            let event: InitEvent
            try {
              event = JSON.parse(payload)
            } catch {
              continue
            }
            applyEvent(event)
            if (event.stage === 'complete') {
              completed = true
            }
            if (event.phase === 'error') {
              setErrored(event.message ?? '未知错误')
              return
            }
          }
        }
        if (completed) {
          toast.success('地图初始化完成')
          onComplete()
        }
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return
        setErrored((e as Error).message)
      }
    })()

    return () => {
      ctrl.abort()
      abortRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, serverId])

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

  const isActive = !errored && (!client.done || !palette.done)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !isActive && onClose()}>
      <DialogContent showCloseButton={!isActive}>
        <DialogHeader>
          <DialogTitle>正在初始化地图</DialogTitle>
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
