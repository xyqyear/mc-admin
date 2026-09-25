import { useRestoreRequest } from '@/shared/operations/useRestoreRequest'
import { useState } from 'react'
import type { RestoreRequest } from '@/features/world/restore/contracts'

type RestorationCommand = { kind: 'restore'; request: RestoreRequest } | { kind: 'rollback'; restorationId: string }

export function useRestorationStream(serverId: string) {
  const [command, setCommand] = useState<RestorationCommand | null>(null)
  const stream = useRestoreRequest()
  const start = (next: RestorationCommand) => {
    setCommand(structuredClone(next))
    stream.start(next.kind === 'rollback'
      ? { url: `/servers/${serverId}/world-restore/restorations/${next.restorationId}/rollback` }
      : { url: `/servers/${serverId}/world-restore/restore`, body: next.request })
  }
  const reset = () => { stream.reset(); setCommand(null) }
  return { command, state: stream.state, start, reset }
}
