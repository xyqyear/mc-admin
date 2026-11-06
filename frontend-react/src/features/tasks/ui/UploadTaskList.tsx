import { Upload, Trash2 } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Progress } from '@/shared/ui/progress'
import { formatFileSize } from '@/shared/utils/formatUtils'
import { clearFinishedUploads, isUploadActive, removeUpload, reopenUpload, useUploadStore, type UploadTask } from '../uploads'

function UploadItem({ task }: { task: UploadTask }) {
  const title = task.kind === 'archive' && task.fileNames.some(name => task.message.includes(name))
    ? task.message
    : `${task.message} ${task.title}${task.fileCount > 1 ? ` 等 ${task.fileCount} 个文件` : ''}`
  return <div className="border-b px-3 py-2 last:border-b-0">
    <div className="flex items-center gap-2 text-xs">
      <Upload aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
      <button className="min-w-0 flex-1 truncate text-left font-medium hover:underline focus-visible:underline" onClick={() => reopenUpload(task.id)} aria-label={`查看上传：${task.title}`} title={task.kind === 'files' ? `${task.serverId} · ${task.basePath}` : task.title}>
        {title}
      </button>
      <span className="shrink-0">{Math.round(task.progress)}%</span>
      {!isUploadActive(task) && (
        <Button variant="ghost" size="icon-sm" aria-label={`移除上传：${task.title}`} onClick={() => removeUpload(task.id)}>
          <Trash2 className="size-3" />
        </Button>
      )}
    </div>
    <Progress value={task.progress} className="mt-1 h-1" />
    <div className="mt-1 text-xs text-muted-foreground">
      {formatFileSize(task.totalSize)}
      {task.detail && <p className={task.status === 'error' ? 'text-destructive' : ''}>{task.detail}</p>}
    </div>
  </div>
}

export default function UploadTaskList() {
  const tasks = useUploadStore(state => state.tasks)
  const all = tasks.filter(task => task.started).toSorted((a, b) => b.startTime - a.startTime)
  if (!all.length) return <p className="p-6 text-center text-xs text-muted-foreground">暂无上传任务</p>
  const active = all.filter(isUploadActive)
  const finished = all.filter(task => !isUploadActive(task))
  return <div className="max-h-80 overflow-y-auto">
    {active.length > 0 && <>
      <p className="bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">进行中 ({active.length})</p>
      {active.map(task => <UploadItem key={task.id} task={task} />)}
    </>}
    {finished.length > 0 && <>
      <div className="flex items-center justify-between bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
        <span>已结束 ({finished.length})</span>
        <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={clearFinishedUploads}>清除已结束</Button>
      </div>
      {finished.map(task => <UploadItem key={task.id} task={task} />)}
    </>}
  </div>
}
