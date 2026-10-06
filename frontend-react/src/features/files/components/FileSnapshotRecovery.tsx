import { useState, type ReactNode } from 'react'
import { fileSnapshotScope, useCreateSnapshot, useSnapshotOperation } from '@/features/backups/commands'
import type { SnapshotPreviewRequest, SnapshotScope } from '@/features/backups/contracts'
import { useSnapshotTarget, useEligibleSnapshots } from '@/features/backups/queries';
import { SnapshotPreviewDialog } from '@/features/backups/ui/SnapshotPreviewDialog'
import { RestorationHistoryDialog } from '@/features/backups/ui/RestorationHistoryDialog'
import { SnapshotCreateDialog } from '@/features/backups/ui/SnapshotCreateDialog'
import { SnapshotRecoveryContext } from '../snapshotRecoveryContext'
import { SnapshotSelectionDialog } from './SnapshotSelectionDialog'

export function FileSnapshotRecovery({ serverId, children }: { serverId: string; children: ReactNode }) {
  const [selection, setSelection] = useState<{ paths: string[]; label: string } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [preview, setPreview] = useState<SnapshotPreviewRequest | null>(null)
  const scope = fileSnapshotScope(serverId, selection?.paths ?? ['/'])
  const operation = useSnapshotOperation(scope, { resumeAny: true })
  const target = useSnapshotTarget(selection ? scope : null)
  const snapshots = useEligibleSnapshots(selection ? scope : null)
  const creation = useCreateSnapshot()
  const [createRequest, setCreateRequest] = useState<{ scope: SnapshotScope; label: string } | null>(null)
  const close = () => { if (!operation.state.active) { operation.reset(); setSelection(null) } }
  const busy = operation.busy || creation.isPending

  return <SnapshotRecoveryContext.Provider value={{
    busy,
    create: (paths, label) => setCreateRequest({ scope: fileSnapshotScope(serverId, [...paths]), label }),
    restore: (paths, label) => { operation.reset(); setSelection({ paths: [...paths], label: label ?? paths.join('、') }) },
    history: () => setHistoryOpen(true),
  }}>
    {children}
    {operation.observationMessage && <p role="status" className="text-sm text-muted-foreground">{operation.observationMessage}</p>}
    <SnapshotCreateDialog request={createRequest} creation={creation} onClose={() => setCreateRequest(null)} />
    <SnapshotSelectionDialog
      open={!historyOpen && (!!selection || operation.state.active || operation.state.done || !!operation.state.error)}
      onCancel={close} onCloseAfterRestore={close}
      snapshots={snapshots.data?.snapshots ?? []} loading={snapshots.isLoading}
      filePath={selection?.label ?? '正在执行的恢复'} isServerMode={selection?.paths.length === 1 && selection.paths[0] === '/'}
      onRestore={id => void operation.start(id)}
      restoreLoading={busy || target.data?.allowed !== true || snapshots.isError}
      onPreview={id => setPreview({ scope, source_snapshot_id: id })}
      previewLoading={!!preview || busy || target.data?.allowed !== true || snapshots.isError}
      restoreState={operation.state}
      notice={snapshots.isError ? '加载可恢复快照失败，请关闭后重试' : target.isError ? '暂时无法检查忽略规则，请稍后重试' : target.data?.reason ?? (target.data?.skipped_count ? '所选范围包含忽略目录，创建与恢复会跳过这些内容。' : null)}
    />
    <SnapshotPreviewDialog request={preview} onClose={() => setPreview(null)} onRestore={id => {
      if (preview) void operation.start(preview.source_snapshot_id, id).then(() => setPreview(null))
    }} />
    <RestorationHistoryDialog open={historyOpen} onClose={() => setHistoryOpen(false)} scope={scope} />
  </SnapshotRecoveryContext.Provider>
}
