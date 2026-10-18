import { Button } from '@/shared/ui/button'
import { useTask } from '../queries'

export function TaskResultFeedback({ taskId }: { taskId?: string | null }) {
  const task = useTask(taskId ?? '')
  if (!taskId || !task.isAwaitingResult) return null
  return (
    <div role="status" className="space-y-2 text-sm text-muted-foreground">
      <p>{task.resultError ? '任务已结束，但完整结果读取失败。请重试读取，无需重新执行任务。' : '任务已结束，正在读取完整结果。'}</p>
      {task.resultError && <Button type="button" variant="outline" size="sm" disabled={task.isFetching} onClick={() => { void task.retryResult() }}>重试读取结果</Button>}
    </div>
  )
}
