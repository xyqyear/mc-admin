import { useEffect } from 'react'
import { clearBrowserUploads, useUploadStore } from '@/features/tasks/uploads'
import ArchiveUploadDialog from '@/features/archives/ui/ArchiveUploadDialog'
import { MultiFileUploadDialog } from '@/features/files/ui/uploads'

export function UploadHost() {
  const tasks = useUploadStore(state => state.tasks)
  const visibleId = useUploadStore(state => state.visibleId)
  useEffect(() => clearBrowserUploads, [])
  return tasks.map(task => task.kind === 'archive'
    ? <ArchiveUploadDialog key={task.id} taskId={task.id} open={visibleId === task.id} initialFiles={task.files} />
    : <MultiFileUploadDialog key={task.id} taskId={task.id} open={visibleId === task.id} serverId={task.serverId} basePath={task.basePath} initialFiles={task.files} />)
}
