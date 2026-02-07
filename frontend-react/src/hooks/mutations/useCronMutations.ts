import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { cronApi, type CreateCronJobRequest, type CronJob, type UpdateCronJobRequest } from '@/hooks/api/cronApi'
import { queryKeys } from '@/utils/api'

export const useCronMutations = () => {
  const queryClient = useQueryClient()
  const { message } = App.useApp()

  const shouldInvalidateRestartSchedule = (cronjobId: string, identifier?: string) => {
    if (identifier) {
      return identifier === 'restart_server'
    }

    const detail = queryClient.getQueryData<CronJob>(queryKeys.cron.detail(cronjobId))
    if (detail?.identifier) {
      return detail.identifier === 'restart_server'
    }

    const listQueries = queryClient.getQueriesData<CronJob[]>({
      queryKey: queryKeys.cron.all,
    })
    for (const [, jobs] of listQueries) {
      const job = jobs?.find((item) => item.cronjob_id === cronjobId)
      if (job?.identifier) {
        return job.identifier === 'restart_server'
      }
    }

    return false
  }

  // Create cron job mutation
  const useCreateCronJob = () => {
    return useMutation({
      mutationFn: (request: CreateCronJobRequest) => cronApi.createCronJob(request),
      onSuccess: (data, request) => {
        message.success(`任务创建成功: ${data.cronjob_id}`)
        // Invalidate relevant queries
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })

        // 如果是restart_server类型的任务，失效所有restart-schedule查询
        if (request.identifier === 'restart_server') {
          queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
        }
      },
      onError: (error: any) => {
        message.error(`创建任务失败: ${error.response?.data?.detail || error.message}`)
      }
    })
  }

  // Update cron job mutation
  const useUpdateCronJob = () => {
    return useMutation({
      mutationFn: ({ cronjobId, request }: { cronjobId: string; request: UpdateCronJobRequest }) =>
        cronApi.updateCronJob(cronjobId, request),
      onSuccess: (_, { cronjobId, request }) => {
        message.success('任务更新成功')
        // Invalidate job detail query and job list
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        if (shouldInvalidateRestartSchedule(cronjobId, request.identifier)) {
          queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
        }
      },
      onError: (error: any) => {
        message.error(`更新任务失败: ${error.response?.data?.detail || error.message}`)
      }
    })
  }

  // Pause cron job mutation
  const usePauseCronJob = () => {
    return useMutation({
      mutationFn: (cronjobId: string) => cronApi.pauseCronJob(cronjobId),
      onSuccess: (_, cronjobId) => {
        message.success('任务已暂停')
        const shouldInvalidate = shouldInvalidateRestartSchedule(cronjobId)
        // Invalidate job detail query and job list
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        if (shouldInvalidate) {
          queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
        }
      },
      onError: (error: any) => {
        message.error(`暂停任务失败: ${error.response?.data?.detail || error.message}`)
      }
    })
  }

  // Resume cron job mutation
  const useResumeCronJob = () => {
    return useMutation({
      mutationFn: (cronjobId: string) => cronApi.resumeCronJob(cronjobId),
      onSuccess: (_, cronjobId) => {
        message.success('任务已恢复')
        const shouldInvalidate = shouldInvalidateRestartSchedule(cronjobId)
        // Invalidate job detail query and job list
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        if (shouldInvalidate) {
          queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
        }
      },
      onError: (error: any) => {
        message.error(`恢复任务失败: ${error.response?.data?.detail || error.message}`)
      }
    })
  }

  // Cancel cron job mutation
  const useCancelCronJob = () => {
    return useMutation({
      mutationFn: (cronjobId: string) => cronApi.cancelCronJob(cronjobId),
      onSuccess: (_, cronjobId) => {
        message.success('任务已取消')
        const shouldInvalidate = shouldInvalidateRestartSchedule(cronjobId)
        // Invalidate job detail query and job list
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.detail(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.nextRunTime(cronjobId) })
        queryClient.invalidateQueries({ queryKey: queryKeys.cron.all })
        if (shouldInvalidate) {
          queryClient.invalidateQueries({ queryKey: queryKeys.restartSchedule.all })
        }
      },
      onError: (error: any) => {
        message.error(`取消任务失败: ${error.response?.data?.detail || error.message}`)
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
