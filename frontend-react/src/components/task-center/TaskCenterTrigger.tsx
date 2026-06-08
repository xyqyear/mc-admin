import React, { useEffect, useRef, useState } from 'react'
import { ListTodo } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useTaskCenterStore } from '@/stores/useTaskCenterStore'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useDownloadTasks } from '@/stores/useDownloadStore'
import {
  clampTaskCenterTriggerPosition,
  type TaskCenterTriggerPosition,
} from '@/config/taskCenterLayout'

interface DragState {
  pointerId: number
  startX: number
  startY: number
  startPosition: TaskCenterTriggerPosition
  latestPosition: TaskCenterTriggerPosition
  moved: boolean
}

const DRAG_THRESHOLD = 4

const TaskCenterTrigger: React.FC = () => {
  const { isOpen, toggleOpen, triggerPosition, setTriggerPosition } =
    useTaskCenterStore()
  const { useActiveTasks } = useTaskQueries()
  const { data: activeTasks } = useActiveTasks()
  const downloadTasks = useDownloadTasks()
  const [displayPosition, setDisplayPosition] = useState(triggerPosition)
  const [isDragging, setIsDragging] = useState(false)
  const dragStateRef = useRef<DragState | null>(null)
  const suppressClickRef = useRef(false)

  useEffect(() => {
    const syncDisplayPosition = () => {
      if (!dragStateRef.current) {
        setDisplayPosition(
          clampTaskCenterTriggerPosition(
            triggerPosition,
            window.innerWidth,
            window.innerHeight
          )
        )
      }
    }

    syncDisplayPosition()
    window.addEventListener('resize', syncDisplayPosition)
    return () => window.removeEventListener('resize', syncDisplayPosition)
  }, [triggerPosition])

  const activeBackgroundCount = activeTasks?.length || 0
  const activeDownloadCount = downloadTasks.filter(
    (t) => t.status === 'downloading'
  ).length
  const totalActiveCount = activeBackgroundCount + activeDownloadCount

  const handlePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) {
      return
    }

    const startPosition = clampTaskCenterTriggerPosition(
      displayPosition,
      window.innerWidth,
      window.innerHeight
    )
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startPosition,
      latestPosition: startPosition,
      moved: false,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const dragState = dragStateRef.current
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return
    }

    const deltaX = event.clientX - dragState.startX
    const deltaY = event.clientY - dragState.startY
    const moved =
      dragState.moved ||
      Math.hypot(deltaX, deltaY) >= DRAG_THRESHOLD
    const nextPosition = clampTaskCenterTriggerPosition(
      {
        right: dragState.startPosition.right - deltaX,
        bottom: dragState.startPosition.bottom - deltaY,
      },
      window.innerWidth,
      window.innerHeight
    )

    dragStateRef.current = {
      ...dragState,
      latestPosition: nextPosition,
      moved,
    }

    if (moved) {
      setIsDragging(true)
      setDisplayPosition(nextPosition)
      event.preventDefault()
    }
  }

  const finishDrag = (event: React.PointerEvent<HTMLButtonElement>) => {
    const dragState = dragStateRef.current
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return
    }

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }

    dragStateRef.current = null
    setIsDragging(false)

    if (dragState.moved) {
      suppressClickRef.current = true
      setTriggerPosition(dragState.latestPosition)
      window.setTimeout(() => {
        suppressClickRef.current = false
      }, 200)
    }
  }

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      event.preventDefault()
      event.stopPropagation()
      return
    }

    toggleOpen()
  }

  const trigger = (
    <Button
      size="icon"
      variant={isOpen ? 'default' : 'secondary'}
      className={`relative h-12 w-12 touch-none rounded-full shadow-lg ${
        isDragging ? 'cursor-grabbing' : 'cursor-grab'
      }`}
      aria-label="任务中心"
      onClick={handleClick}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishDrag}
      onPointerCancel={finishDrag}
    >
      <ListTodo className="h-5 w-5" />
      {totalActiveCount > 0 && (
        <span className="absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-xs font-medium text-destructive-foreground">
          {totalActiveCount}
        </span>
      )}
    </Button>
  )

  return (
    <div
      className="fixed z-50"
      style={{
        right: displayPosition.right,
        bottom: displayPosition.bottom,
      }}
    >
      {isOpen ? (
        trigger
      ) : (
        <Tooltip>
          <TooltipTrigger className="inline-flex" render={trigger} />
          <TooltipContent side="left">任务中心</TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export default TaskCenterTrigger
