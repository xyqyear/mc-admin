import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { selfCheckApi } from '@/hooks/api/selfCheckApi'
import { queryKeys } from '@/utils/api'

export const useSelfCheckMutations = () => {
  const queryClient = useQueryClient()

  const useRunSelfCheck = () => {
    return useMutation({
      mutationFn: selfCheckApi.runSelfCheck,
      onSuccess: async (result) => {
        if (result.status === 'success') {
          toast.success('自检完成，未发现问题')
        } else {
          toast.warning('自检完成，发现需要处理的项目')
        }
        await queryClient.invalidateQueries({ queryKey: queryKeys.selfCheck.all })
      },
      onError: (error: any) => {
        toast.error(`自检失败: ${error.response?.data?.detail || error.message}`)
      },
    })
  }

  const useRunSelfCheckItem = () => {
    return useMutation({
      mutationFn: selfCheckApi.runSelfCheckItem,
      onSuccess: async (result) => {
        if (result.status === 'success') {
          toast.success('自检项已通过')
        } else {
          toast.warning('自检项仍需要处理')
        }
        await queryClient.invalidateQueries({ queryKey: queryKeys.selfCheck.all })
      },
      onError: (error: any) => {
        toast.error(`自检项失败: ${error.response?.data?.detail || error.message}`)
      },
    })
  }

  return {
    useRunSelfCheck,
    useRunSelfCheckItem,
  }
}
