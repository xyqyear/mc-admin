import { useState, type ReactNode } from 'react'
import { fileSnapshotScope, useCreateSnapshot, useSnapshotOperation } from '@/features/backups/commands'
import type { SnapshotPreviewRequest, SnapshotScope } from '@/features/backups/contracts'
import { useSnapshotTarget, useSnapshotsForPath } from '@/features/backups/queries';
import { SnapshotPreviewDialog } from '@/features/backups/ui/SnapshotPreviewDialog'
import { RestorationHistoryDialog } from '@/features/backups/ui/RestorationHistoryDialog'
import { SnapshotCreateDialog } from '@/features/backups/ui/SnapshotCreateDialog'
import { SnapshotRecoveryContext } from '../snapshotRecoveryContext'
import { SnapshotSelectionDialog } from './SnapshotSelectionDialog'

export function FileSnapshotRecovery({ serverId, children }: { serverId: string; children: ReactNode }) {
  const [path, setPath] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [preview, setPreview] = useState<SnapshotPreviewRequest | null>(null)
  const scope = fileSnapshotScope(serverId, [path ?? '/'])
  const operation = useSnapshotOperation(scope, { resumeAny: true })
  const target = useSnapshotTarget(path ? scope : null)
  const snapshots = useSnapshotsForPath(serverId, path, !!path)
  const creation = useCreateSnapshot()
  const [createRequest, setCreateRequest] = useState<{ scope: SnapshotScope; label: string } | null>(null)
  const close = () => { if (!operation.state.active) { operation.reset(); setPath(null) } }
  const busy = operation.busy || creation.isPending

  return <SnapshotRecoveryContext.Provider value={{
    busy,
    create: (targetPath, label) => setCreateRequest({ scope: fileSnapshotScope(serverId, [targetPath]), label }),
    restore: targetPath => { operation.reset(); setPath(targetPath) },
    history: () => setHistoryOpen(true),
  }}>
    {children}
    {operation.observationMessage && <p role="status" className="text-sm text-muted-foreground">{operation.observationMessage}</p>}
    <SnapshotCreateDialog request={createRequest} creation={creation} onClose={() => setCreateRequest(null)} />
    <SnapshotSelectionDialog
      open={!historyOpen && (!!path || operation.state.active || operation.state.done || !!operation.state.error)}
      onCancel={close} onCloseAfterRestore={close}
      snapshots={snapshots.data ?? []} loading={snapshots.isLoading}
      filePath={path ?? '正在执行的恢复'} isServerMode={path === '/'}
      onRestore={id => void operation.start(id)}
      restoreLoading={busy || target.data?.allowed !== true}
      onPreview={id => setPreview({ scope, source_snapshot_id: id })}
      previewLoading={!!preview || busy || target.data?.allowed !== true}
      restoreState={operation.state}
      notice={target.isError ? '暂时无法检查忽略规则，请稍后重试' : target.data?.reason ?? (target.data?.skipped_count ? '所选范围包含忽略目录，创建与恢复会跳过这些内容。' : null)}
    />
    <SnapshotPreviewDialog request={preview} onClose={() => setPreview(null)} onRestore={id => {
      if (preview) void operation.start(preview.source_snapshot_id, id).then(() => setPreview(null))
    }} />
    <RestorationHistoryDialog open={historyOpen} onClose={() => setHistoryOpen(false)} scope={scope} />
  </SnapshotRecoveryContext.Provider>
}
