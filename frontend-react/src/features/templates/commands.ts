import { getErrorMessage, type ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys } from "@/shared/http/api";
import { templateApi } from "@/features/templates/api";
import type { TemplateCreateRequest, TemplateUpdateRequest, VariableDefinition } from '@/features/templates/contracts';

export const useTemplateMutations = () => {
  const queryClient = useQueryClient();

  const useCreateTemplate = () => {
    return useMutation({
      mutationFn: (request: TemplateCreateRequest) =>
        templateApi.createTemplate(request),
      onSuccess: () => {
        toast.success("模板创建成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.list(),
        });
      },
      onError: (error: ApiError) => {
        toast.error(`创建失败: ${getErrorMessage(error)}`);
      },
    });
  };

  const useUpdateTemplate = () => {
    return useMutation({
      mutationFn: ({
        id,
        request,
      }: {
        id: number;
        request: TemplateUpdateRequest;
      }) => templateApi.updateTemplate(id, request),
      onSuccess: (_, { id }) => {
        toast.success("模板更新成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.list(),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.detail(id),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.schema(id),
        });
        // Refresh has_template_update on dependent server configs.
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.serverConfigs(),
        });
      },
      onError: (error: ApiError) => {
        toast.error(`更新失败: ${getErrorMessage(error)}`);
      },
    });
  };

  const useDeleteTemplate = () => {
    return useMutation({
      mutationFn: (id: number) => templateApi.deleteTemplate(id),
      onSuccess: () => {
        toast.success("模板删除成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.list(),
        });
        // Refresh template_deleted on dependent server configs.
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.serverConfigs(),
        });
      },
      onError: (error: ApiError) => {
        toast.error(`删除失败: ${getErrorMessage(error)}`);
      },
    });
  };

  const usePreviewRenderedYaml = () => {
    return useMutation({
      mutationFn: ({
        id,
        variableValues,
      }: {
        id: number;
        variableValues: Record<string, unknown>;
      }) => templateApi.previewRenderedYaml(id, variableValues),
      onError: (error: ApiError) => {
        toast.error(`预览失败: ${getErrorMessage(error)}`);
      },
    });
  };

  const useUpdateDefaultVariables = () => {
    return useMutation({
      mutationFn: (variables: VariableDefinition[]) =>
        templateApi.updateDefaultVariables(variables),
      onSuccess: () => {
        toast.success("默认变量配置已更新");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.defaultVariables(),
        });
      },
      onError: (error: ApiError) => {
        toast.error(`更新失败: ${getErrorMessage(error)}`);
      },
    });
  };

  return {
    useCreateTemplate,
    useUpdateTemplate,
    useDeleteTemplate,
    usePreviewRenderedYaml,
    useUpdateDefaultVariables,
  };
};
