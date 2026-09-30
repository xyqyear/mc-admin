import type { BackgroundTask } from '@/features/tasks/contracts'
import { openTaskCenter } from '@/features/tasks/commands'
import { Button } from '@/shared/ui/button'
import { Spinner } from '@/shared/ui/spinner'

export function SnapshotCreationStatus({ pending, task }: { pending: boolean; task: BackgroundTask | null }) {
  if (!pending) return null
  return <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
    <Spinner className="h-4 w-4" />
    <span>{task?.message || '正在提交快照任务'}</span>
    {task?.progress != null && <span>{Math.round(task.progress)}%</span>}
    {task && <Button variant="link" size="sm" onClick={openTaskCenter}>查看任务</Button>}
  </div>
}
