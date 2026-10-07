import { Database, History } from 'lucide-react'
import { fileSnapshotScope } from '@/features/backups/commands'
import { useSnapshotTarget } from '@/features/backups/queries'
import { Button } from '@/shared/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/shared/ui/tooltip'
import type { FileItem } from '../contracts'
import { useFileSnapshotRecovery } from '../snapshotRecoveryContext'

export default function FileSnapshotActions({ file, serverId, path, isServerMode = false }: {
  file?: FileItem
  serverId: string
  path?: string
  isServerMode?: boolean
}) {
  const recovery = useFileSnapshotRecovery()
  const actualPath = path || file?.path || '/'
  const label = isServerMode ? '服务器数据目录' : file?.name || actualPath
  const target = useSnapshotTarget(fileSnapshotScope(serverId, [actualPath]))
  const disabled = recovery.busy || target.data?.allowed !== true || target.isError
  const notice = target.isError ? '暂时无法检查忽略规则'
    : target.isPending ? '正在检查忽略规则'
      : target.data?.reason ?? (target.data?.skipped_count ? '所选范围包含忽略目录，创建与恢复会跳过这些内容' : null)
  return <div className="flex flex-wrap items-center gap-1">
    <Tooltip>
      <TooltipTrigger render={<span />}>
        <Button variant="outline" size={isServerMode ? 'default' : 'icon-sm'}
          aria-label={`为 ${label} 创建快照`} disabled={disabled}
          onClick={() => recovery.create([actualPath], label)}>
          <Database className="h-4 w-4" />{isServerMode && '创建快照'}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{notice ?? `为 ${label} 创建快照`}</TooltipContent>
    </Tooltip>
    <Tooltip>
      <TooltipTrigger render={<span />}>
        <Button variant={isServerMode ? 'default' : 'outline'} size={isServerMode ? 'default' : 'icon-sm'}
          aria-label={`恢复 ${label}`} disabled={disabled} onClick={() => recovery.restore([actualPath], label)}>
          <History className="h-4 w-4" />{isServerMode && '快照恢复'}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{notice ?? `恢复 ${label}`}</TooltipContent>
    </Tooltip>
    {isServerMode && <Button variant="outline" onClick={recovery.history}>恢复历史</Button>}
    {isServerMode && notice && <span className="text-xs text-muted-foreground">{notice}</span>}
  </div>
}
