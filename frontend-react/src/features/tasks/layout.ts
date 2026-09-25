import type { CSSProperties } from 'react'

export interface TaskCenterTriggerPosition {
  right: number
  bottom: number
}

export const TASK_CENTER_TRIGGER_SIZE = 48
export const TASK_CENTER_EDGE_GAP = 16
export const TASK_CENTER_PANEL_GAP = 16
export const TASK_CENTER_PANEL_WIDTH = 360
export const TASK_CENTER_PANEL_EXPECTED_HEIGHT = 400
export const DEFAULT_TASK_CENTER_TRIGGER_POSITION: TaskCenterTriggerPosition = {
  right: 24,
  bottom: 88,
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), Math.max(min, max))

export const clampTaskCenterTriggerPosition = (
  position: TaskCenterTriggerPosition,
  viewportWidth: number,
  viewportHeight: number
): TaskCenterTriggerPosition => ({
  right: clamp(
    position.right,
    TASK_CENTER_EDGE_GAP,
    viewportWidth - TASK_CENTER_TRIGGER_SIZE - TASK_CENTER_EDGE_GAP
  ),
  bottom: clamp(
    position.bottom,
    TASK_CENTER_EDGE_GAP,
    viewportHeight - TASK_CENTER_TRIGGER_SIZE - TASK_CENTER_EDGE_GAP
  ),
})

export const getTaskCenterPanelStyle = (
  position: TaskCenterTriggerPosition,
  viewportWidth: number,
  viewportHeight: number
): CSSProperties => {
  const right = clamp(
    position.right,
    TASK_CENTER_EDGE_GAP,
    viewportWidth - TASK_CENTER_PANEL_WIDTH - TASK_CENTER_EDGE_GAP
  )
  const aboveBottom =
    position.bottom + TASK_CENTER_TRIGGER_SIZE + TASK_CENTER_PANEL_GAP
  const roomAbove = viewportHeight - aboveBottom - TASK_CENTER_EDGE_GAP

  if (roomAbove >= TASK_CENTER_PANEL_EXPECTED_HEIGHT) {
    return {
      right,
      bottom: aboveBottom,
      maxHeight: `calc(100vh - ${aboveBottom + TASK_CENTER_EDGE_GAP}px)`,
    }
  }

  const top = clamp(
    viewportHeight - position.bottom + TASK_CENTER_PANEL_GAP,
    TASK_CENTER_EDGE_GAP,
    viewportHeight - TASK_CENTER_EDGE_GAP
  )

  return {
    right,
    top,
    maxHeight: `calc(100vh - ${top + TASK_CENTER_EDGE_GAP}px)`,
  }
}
