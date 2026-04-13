import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/components/common/StatusBadge'

interface PlayerOnlineBadgeProps {
  online: boolean
  onlineLabel?: string
  offlineLabel?: string
}

export function PlayerOnlineBadge({
  online,
  onlineLabel = '在线',
  offlineLabel = '离线',
}: PlayerOnlineBadgeProps) {
  if (online) {
    return <StatusBadge tone="success">{onlineLabel}</StatusBadge>
  }
  return <Badge variant="secondary">{offlineLabel}</Badge>
}
