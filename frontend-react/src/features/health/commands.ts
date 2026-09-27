import { waitForTaskResult } from '@/features/tasks/commands'
import type { SelfCheckRunResult } from './contracts'
import { getErrorMessage, type ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { selfCheckApi } from '@/features/health/api'
import { queryKeys } from '@/shared/http/api'

export const useSelfCheckMutations = () => {
  const queryClient = useQueryClient()

  const useRunSelfCheckItem = () => {
    return useMutation({
      mutationFn: async (checkId: string) => waitForTaskResult<SelfCheckRunResult>(queryClient, await selfCheckApi.runSelfCheckItem(checkId)),
      onSuccess: async (result) => {
        if (result.status === 'success') {
          toast.success('自检项已通过')
        } else {
          toast.warning('自检项仍需要处理')
        }
        await queryClient.invalidateQueries({ queryKey: queryKeys.selfCheck.all })
      },
      onError: (error: ApiError) => {
        toast.error(`自检项失败: ${getErrorMessage(error)}`)
      },
    })
  }

  return {
    useRunSelfCheckItem,
  }
}
