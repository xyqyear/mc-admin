import { Button } from '@/shared/ui/button'
import { useState, type ReactNode } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { formatDateTime } from '@/shared/utils/formatUtils'
import { useSnapshotOperation } from '../commands'
import { useRestorationHistory } from '../queries'
import type { Restoration, RestorationFilters, SnapshotScope } from '../contracts'
import { RestoreProgressCard } from './RestoreProgressCard'

const labels: Record<Restoration['status'], string> = {
  pending: '等待执行', running: '正在恢复', succeeded: '已完成', failed: '失败',
  cancelled: '已取消', interrupted: '已中断',
}

export function RestorationHistoryDialog({ open, onClose, scope, serverStopped, renderActions }: {
  open: boolean; onClose: () => void; scope: SnapshotScope
  serverStopped?: boolean
  renderActions?: (row: Restoration) => ReactNode
}) {
  const operation = useSnapshotOperation(scope, { resumeAny: true, enabled: open })
  const [offset, setOffset] = useState(0)
  const [filters, setFilters] = useState<RestorationFilters>({})
  const history = useRestorationHistory('server_id' in scope ? scope.server_id : undefined, offset, open, filters)
  const { confirm, confirmDialog } = useConfirm()
  const progress = operation.state.active || operation.state.done || !!operation.state.error
  return <Dialog open={open} onOpenChange={next => { if (!next && !operation.state.active) { operation.reset(); onClose() } }}>
    <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>恢复历史</DialogTitle>
        <DialogDescription>回滚会先保存当前状态，再恢复原操作之前的内容；忽略目录保持不变。</DialogDescription>
      </DialogHeader>
      <div className="flex flex-wrap gap-2 text-sm">
        <label>范围 <select aria-label="筛选恢复范围" className="rounded-md border bg-background p-1" value={filters.kind ?? ''} onChange={event => { setOffset(0); setFilters({ ...filters, kind: event.target.value as RestorationFilters['kind'] || undefined }) }}>
          <option value="">全部</option><option value="paths">文件路径</option><option value="world">世界</option><option value="server">服务器项目</option><option value="global">全局</option>
        </select></label>
        <label>状态 <select aria-label="筛选恢复状态" className="rounded-md border bg-background p-1" value={filters.status ?? ''} onChange={event => { setOffset(0); setFilters({ ...filters, status: event.target.value as RestorationFilters['status'] || undefined }) }}>
          <option value="">全部</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>入口 <select aria-label="筛选恢复入口" className="rounded-md border bg-background p-1" value={filters.entry_point ?? ''} onChange={event => { setOffset(0); setFilters({ ...filters, entry_point: event.target.value as RestorationFilters['entry_point'] || undefined }) }}>
          <option value="">全部</option><option value="files">文件</option><option value="world">地图</option><option value="snapshots">快照</option><option value="history">历史回滚</option>
        </select></label>
      </div>
      {operation.observationMessage && <p role="status">{operation.observationMessage}</p>}
      {progress && <RestoreProgressCard state={operation.state} />}
      {history.isError && <p role="alert">无法读取恢复历史。<Button variant="outline" onClick={() => void history.refetch()}>重试</Button></p>}
      {history.isPending && <p>正在读取恢复历史…</p>}
      {history.data?.restorations.map(row => <div className="space-y-2 rounded-md border p-3" key={row.id}>
        <div className="flex items-center justify-between gap-2">
          <span>{row.is_rollback ? '回滚' : '恢复'} · {formatDateTime(row.started_at)} · <span>{labels[row.status]}</span></span>
          <div className="flex items-center gap-2">{renderActions?.(row)}<Button variant="outline" size="sm" disabled={!row.rollback_available || operation.busy || (row.scope?.kind === 'world' && serverStopped === false)} onClick={() => confirm({
            title: '确认回滚恢复',
            description: '所选范围内后来的修改会被替换。回滚前会创建安全快照，之后仍可再次回滚。',
            confirmText: '开始回滚', onConfirm: () => operation.rollback(row.id),
          })}>回滚</Button></div>
        </div>
        <p className="text-xs text-muted-foreground">源快照 <span>{row.source_snapshot_id.slice(0, 8)}</span> · 安全快照 <span>{row.safety_snapshot_id?.slice(0, 8) ?? '尚未创建'}</span></p>
        {row.server_id && <p className="text-xs text-muted-foreground">服务器 {row.server_id} · 实例 {row.server_generation ?? '归属不明'} · 入口 {row.entry_point === 'world' ? '地图' : row.entry_point === 'files' ? '文件' : row.entry_point === 'history' ? '历史回滚' : '快照'}</p>}
        {row.scope?.kind === 'global' && <p className="text-xs text-muted-foreground">全局恢复 · {row.targets.map(target => `${target.server_id}（实例 ${target.generation ?? '归属不明'}）`).join('、')}</p>}
        {!row.source_snapshot_exists && <p className="text-xs text-muted-foreground">源快照已不存在</p>}
        {row.scope?.kind === 'paths' && <p className="text-xs break-all">{row.scope.paths.join('、')}</p>}
        {row.scope?.kind === 'world' && <p className="text-xs">{{ world: '整个世界', dimension: '维度', regions: '区域', chunks: '区块' }[row.scope.selection.type]} {row.scope.selection.region_dir_relpath}</p>}
        {row.scope?.kind === 'world' && serverStopped === false && <p className="text-xs text-muted-foreground">请先停止服务器再回滚世界数据</p>}
        {row.error_message && <p className="text-sm text-destructive">{row.error_message}</p>}
        {row.rollback_unavailable_reason && <p className="text-xs text-muted-foreground">{row.rollback_unavailable_reason}</p>}
      </div>)}
      {history.data?.total === 0 && <p>暂无恢复记录</p>}
      {!!history.data?.total && <div className="flex items-center justify-end gap-2">
        <span className="text-sm">共 {history.data.total} 条</span>
        <Button variant="outline" disabled={offset === 0 || operation.state.active} onClick={() => setOffset(value => Math.max(0, value - 50))}>上一页</Button>
        <Button variant="outline" disabled={offset + 50 >= history.data.total || operation.state.active} onClick={() => setOffset(value => value + 50)}>下一页</Button>
      </div>}
      {confirmDialog}
    </DialogContent>
  </Dialog>
}
