// Minimal shape needed to drive the progress reducer. Both
// world-restore RestoreEvent and snapshots SnapshotRestoreEvent satisfy it,
// so the same reducer powers both flows.
export interface RestoreProgressEvent {
  event_type: string
  message?: string
  percent?: number
}

export interface RestoreProgressState {
  active: boolean
  percent: number
  message: string
  log: string[]
  done: boolean
  error: string | null
}

export const initialProgress: RestoreProgressState = {
  active: false,
  percent: 0,
  message: '',
  log: [],
  done: false,
  error: null,
}

const STAGE_LABEL: Record<string, string> = {
  start: '准备',
  safety_snapshot: '创建安全快照',
  stage: '提取快照内容',
  merge_region: '合并区块',
  restore: '恢复文件',
  invalidate_cache: '刷新地图缓存',
  complete: '完成',
  error: '错误',
}

// Pure-function reducer used by both the snapshot picker and the history
// drawer when consuming the restore SSE. Keeps event handling consistent
// across the two consumers.
export function applyRestoreEvent(
  prev: RestoreProgressState,
  ev: RestoreProgressEvent,
): RestoreProgressState {
  const stage = STAGE_LABEL[ev.event_type] ?? ev.event_type
  const text = ev.message ?? stage
  const log = [...prev.log, `[${stage}] ${text}`].slice(-50)
  if (ev.event_type === 'error') {
    return {
      ...prev,
      active: false,
      done: false,
      message: text,
      error: ev.message ?? '未知错误',
      log,
    }
  }
  if (ev.event_type === 'complete') {
    return {
      ...prev,
      active: false,
      done: true,
      percent: 100,
      message: text,
      log,
    }
  }
  return {
    ...prev,
    active: true,
    percent: ev.percent ?? prev.percent,
    message: text,
    log,
  }
}
