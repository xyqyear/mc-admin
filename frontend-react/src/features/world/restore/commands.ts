import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { createSnapshot } from '@/features/backups/commands'
import type { ApiError } from '@/shared/http/api'
import type { RestorationSelection } from '@/features/backups/contracts'
import { queryKeys } from '@/shared/http/api'

export const useWorldRestoreMutations = () => {
  const queryClient = useQueryClient()

  const useCreateWorldSnapshot = (serverId: string) =>
    useMutation({
      mutationFn: (selection: RestorationSelection) =>
        createSnapshot(queryClient, { kind: 'world', server_id: serverId, selection }),
      onSuccess: (data) => {
        toast.success(`快照创建成功: ${data.snapshot.short_id}`)
        queryClient.invalidateQueries({ queryKey: queryKeys.worldRestore.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.snapshots.all })
      },
      onError: (error: ApiError) => {
        const detail = error?.message ?? '未知错误'
        toast.error(`快照创建失败: ${detail}`)
      },
    })

  return { useCreateWorldSnapshot }
}
