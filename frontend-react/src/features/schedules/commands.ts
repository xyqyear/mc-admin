import { getErrorMessage, type ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { cronApi } from '@/features/schedules/api';
import type { CreateCronJobRequest, UpdateCronJobRequest } from '@/features/schedules/contracts';
import { queryKeys } from '@/shared/http/api'

export const useCronMutations = () => {
  const queryClient = useQueryClient()

  const useCreateCronJob = () => {
    return useMutation({
      mutationFn: (request: CreateCronJobRequest) => cronApi.createCronJob(request),
      onSuccess: (data) => {
        toast.success(`任务创建成功: ${data.cronjob_id}`)
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
      },
      onError: (error: ApiError) => {
        toast.error(`创建任务失败: ${getErrorMessage(error)}`)
      }
    })
  }

  const useUpdateCronJob = () => {
    return useMutation({
      mutationFn: ({ cronjobId, request }: { cronjobId: string; request: UpdateCronJobRequest }) =>
        cronApi.updateCronJob(cronjobId, request),
      onSuccess: (_, { cronjobId }) => {
        toast.success('任务更新成功')
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
      },
      onError: (error: ApiError) => {
        toast.error(`更新任务失败: ${getErrorMessage(error)}`)
      }
    })
  }

  const usePauseCronJob = () => {
    return useMutation({
      mutationFn: (cronjobId: string) => cronApi.pauseCronJob(cronjobId),
      onSuccess: (_, cronjobId) => {
        toast.success('任务已暂停')
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
      },
      onError: (error: ApiError) => {
        toast.error(`暂停任务失败: ${getErrorMessage(error)}`)
      }
    })
  }

  const useResumeCronJob = () => {
    return useMutation({
      mutationFn: (cronjobId: string) => cronApi.resumeCronJob(cronjobId),
      onSuccess: (_, cronjobId) => {
        toast.success('任务已恢复')
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
      },
      onError: (error: ApiError) => {
        toast.error(`恢复任务失败: ${getErrorMessage(error)}`)
      }
    })
  }

  const useCancelCronJob = () => {
    return useMutation({
      mutationFn: (cronjobId: string) => cronApi.cancelCronJob(cronjobId),
      onSuccess: (_, cronjobId) => {
        toast.success('任务已取消')
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
      },
      onError: (error: ApiError) => {
        toast.error(`取消任务失败: ${getErrorMessage(error)}`)
      }
    })
  }

  return {
    useCreateCronJob,
    useUpdateCronJob,
    usePauseCronJob,
    useResumeCronJob,
    useCancelCronJob
  }
}
