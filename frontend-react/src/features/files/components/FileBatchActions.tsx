import { useEffect, useRef, useState } from 'react'
import { Archive, Database, Download, History, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/shared/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/shared/ui/tooltip'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { fileSnapshotScope } from '@/features/backups/commands'
import { useSnapshotTarget } from '@/features/backups/queries'
import { useCreateArchive, useArchiveDownload } from '@/features/archives/commands'
import { useTask } from '@/features/tasks/queries'
import { useBulkDeleteFiles } from '../commands'
import { useDirectoryDownload } from '../useDirectoryDownload'
import { useFileSnapshotRecovery } from '../snapshotRecoveryContext'
import { DirectoryDownloadDialog, type DirectoryDownloadRequest } from './dialogs/DirectoryDownloadDialog'
import CompressionConfirmDialog from './dialogs/CompressionConfirmDialog'
import CompressionResultDialog from './dialogs/CompressionResultDialog'

export function FileBatchActions({ serverId, paths, basePath, onDeleted }: {
  serverId: string
  paths: string[]
  basePath: string
  onDeleted?: (paths: string[]) => void
}) {
  const recovery = useFileSnapshotRecovery()
  const target = useSnapshotTarget(paths.length ? fileSnapshotScope(serverId, paths) : null)
  const download = useDirectoryDownload(serverId)
  const deletion = useBulkDeleteFiles(serverId)
  const packing = useCreateArchive()
  const archiveDownload = useArchiveDownload()
  const { confirm, confirmDialog } = useConfirm()
  const [downloadRequest, setDownloadRequest] = useState<DirectoryDownloadRequest | null>(null)
  const [packPaths, setPackPaths] = useState<string[] | null>(null)
  const [packTaskId, setPackTaskId] = useState<string | null>(null)
  const packSubmitting = useRef(false)
  const [archive, setArchive] = useState<string | null>(null)
  const [failures, setFailures] = useState<{ path: string; message: string }[]>([])
  const { data: task } = useTask(packTaskId ?? '')
  const packBusy = packing.isPending || !!packTaskId
  useEffect(() => {
    if (!task || !packTaskId) return
    if (task.status === 'completed') {
      const filename = task.result?.filename
      if (typeof filename === 'string') setArchive(filename)
      setPackPaths(null)
      setPackTaskId(null)
    } else if (task.status === 'failed' || task.status === 'cancelled') {
      toast.error(task.error || '打包任务未完成')
      setPackTaskId(null)
    }
  }, [task, packTaskId])
  const snapshotNotice = target.isError ? '暂时无法检查忽略规则'
    : target.isPending ? '正在检查忽略规则'
      : target.data?.reason ?? (target.data?.skipped_count ? '所选范围包含忽略目录，创建与恢复会跳过这些内容' : null)
  const snapshotDisabled = recovery.busy || target.data?.allowed !== true
  const label = `选中的 ${paths.length} 个条目`
  const snapshotButton = (restore: boolean) => <Tooltip>
    <TooltipTrigger render={<span />}><Button variant="outline" disabled={snapshotDisabled} onClick={() => restore ? recovery.restore([...paths], label) : recovery.create([...paths], label)}>
      {restore ? <History className="mr-2 size-4" /> : <Database className="mr-2 size-4" />}{restore ? '快照恢复' : '创建快照'}
    </Button></TooltipTrigger><TooltipContent>{snapshotNotice ?? (restore ? '从快照恢复所选条目' : '为所选条目创建一个快照')}</TooltipContent>
  </Tooltip>
  return <div role="toolbar" aria-label="所选文件操作" className="space-y-2">
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-muted-foreground">已选择 {paths.length} 个条目</span>
      {snapshotButton(false)}{snapshotButton(true)}
      <Tooltip><TooltipTrigger render={<span />}><Button variant="outline" disabled={!download.supported} onClick={() => setDownloadRequest({ paths: [...paths], basePath })}><Download className="mr-2 size-4" />下载到文件夹</Button></TooltipTrigger><TooltipContent>{download.reason ?? '直接保存到本地文件夹，无需打包'}</TooltipContent></Tooltip>
      <Button variant="outline" disabled={packBusy} onClick={() => setPackPaths([...paths])}><Archive className="mr-2 size-4" />打包所选</Button>
      <Button variant="destructive" disabled={deletion.isPending} onClick={() => {
        const acceptedPaths = [...paths]
        confirm({ title: '确认批量删除', description: `将删除 ${acceptedPaths.length} 个条目及所选目录的全部内容，此操作不可撤销。`, variant: 'destructive', confirmText: '删除', onConfirm: async () => {
          try {
          const result = await deletion.mutateAsync(acceptedPaths)
          setFailures(result.results.filter(item => item.status !== 'deleted').map(item => ({ path: item.path, message: item.message || '未执行' })))
          onDeleted?.(result.results.filter(item => item.status === 'deleted').map(item => '/' + item.path.replace(/^\/+/, '')))
          } catch { /* The mutation displays the failure. */ }
        } })
      }}><Trash2 className="mr-2 size-4" />批量删除</Button>
    </div>
    {failures.length > 0 && <ul role="status" className="text-sm text-destructive">{failures.map(item => <li key={item.path}>{item.path}：{item.message}</li>)}</ul>}
    <DirectoryDownloadDialog key={downloadRequest?.paths.join('\0') ?? 'closed'} serverId={serverId} request={downloadRequest} onClose={() => setDownloadRequest(null)} />
    <CompressionConfirmDialog open={!!packPaths} onCancel={() => setPackPaths(null)} onOk={async () => {
      if (!packPaths || packSubmitting.current || packTaskId) return
      packSubmitting.current = true
      try {
        const result = await packing.mutateAsync({ server_id: serverId, paths: [...packPaths] })
        setPackTaskId(result.task_id)
      } catch { /* The mutation displays the failure. */ }
      finally { packSubmitting.current = false }
    }} confirmLoading={packBusy} task={task} currentPath={basePath} compressionType="batch" selectedPaths={packPaths ?? []} />
    <CompressionResultDialog open={!!archive} onCancel={() => setArchive(null)} archiveFilename={archive ?? ''} message="打包完成" onDownload={() => { if (archive) void archiveDownload.downloadFile('/' + archive, archive) }} downloadLoading={false} />
    {confirmDialog}
  </div>
}
