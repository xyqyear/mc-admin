import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { taskQueryKeys } from '@/features/tasks/queries'
import { getErrorMessage, queryKeys } from '@/shared/http/api'
import { configurationApi } from '@/features/configuration/api'

export function useConfigurationCommands(serverId: string) {
  const client = useQueryClient()
  const submitted = () => {
    void client.invalidateQueries({ queryKey: taskQueryKeys.all })
    void client.invalidateQueries({ queryKey: queryKeys.operations.all })
  }
  const onError = (error: Error) => toast.error(getErrorMessage(error))
  return {
    updateCompose: useMutation({ mutationFn: ({ value, version }: { value: string; version: string }) => configurationApi.updateCompose(serverId, value, version), onSuccess: submitted, onError }),
    updateTemplate: useMutation({ mutationFn: ({ value, version }: { value: Record<string, unknown>; version: string }) => configurationApi.updateServerTemplateConfig(serverId, value, version), onSuccess: submitted, onError }),
    previewTemplate: useMutation({ mutationFn: (value: Record<string, unknown>) => configurationApi.previewServerTemplateConfig(serverId, value), onError }),
    convertToDirect: useMutation({ mutationFn: (version: string) => configurationApi.convertToDirectMode(serverId, version), onSuccess: submitted, onError }),
    extractVariables: useMutation({ mutationFn: (templateId: number) => configurationApi.extractVariables(serverId, templateId), onError }),
    checkConversion: useMutation({ mutationFn: ({ templateId, value }: { templateId: number; value: Record<string, unknown> }) => configurationApi.checkConversion(serverId, templateId, value), onError }),
    convertToTemplate: useMutation({ mutationFn: ({ templateId, value, version }: { templateId: number; value: Record<string, unknown>; version: string }) => configurationApi.convertToTemplateMode(serverId, templateId, value, version), onSuccess: submitted, onError }),
  }
}
