import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys } from "@/utils/api";
import { taskQueryKeys } from "@/hooks/queries/base/useTaskQueries";
import {
  templateApi,
  TemplateCreateRequest,
  TemplateUpdateRequest,
  VariableDefinition,
  ExtractVariablesResponse,
  CheckConversionResponse,
} from "@/hooks/api/templateApi";

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
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          toast.error(`创建失败: ${detail.errors.join(", ")}`);
        } else {
          toast.error(`创建失败: ${detail || error.message}`);
        }
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
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          toast.error(`更新失败: ${detail.errors.join(", ")}`);
        } else {
          toast.error(`更新失败: ${detail || error.message}`);
        }
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
      onError: (error: any) => {
        toast.error(`删除失败: ${error.response?.data?.detail || error.message}`);
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
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          toast.error(`预览失败: ${detail.errors.join(", ")}`);
        } else {
          toast.error(`预览失败: ${detail || error.message}`);
        }
      },
    });
  };

  const useCheckConversion = () => {
    return useMutation<
      CheckConversionResponse,
      any,
      { serverId: string; templateId: number; variableValues: Record<string, unknown> }
    >({
      mutationFn: ({ serverId, templateId, variableValues }) =>
        templateApi.checkConversion(serverId, templateId, variableValues),
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        toast.error(`检查失败: ${detail || error.message}`);
      },
    });
  };

  const useUpdateServerTemplateConfig = () => {
    return useMutation({
      mutationFn: ({
        serverId,
        variableValues,
      }: {
        serverId: string;
        variableValues: Record<string, unknown>;
      }) => templateApi.updateServerTemplateConfig(serverId, variableValues),
      onSuccess: () => {
        toast.success("配置更新成功");
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          toast.error(`更新失败: ${detail.errors.join(", ")}`);
        } else {
          toast.error(`更新失败: ${detail || error.message}`);
        }
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
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        toast.error(`更新失败: ${detail || error.message}`);
      },
    });
  };

  const useConvertToDirectMode = () => {
    return useMutation({
      mutationFn: (serverId: string) => templateApi.convertToDirectMode(serverId),
      onSuccess: (_, serverId) => {
        toast.success("已转换为直接编辑模式");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.serverConfigPreview(serverId),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.serverConfig(serverId),
        });
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        toast.error(`转换失败: ${detail || error.message}`);
      },
    });
  };

  const useExtractVariables = () => {
    return useMutation<
      ExtractVariablesResponse,
      any,
      { serverId: string; templateId: number }
    >({
      mutationFn: ({ serverId, templateId }) =>
        templateApi.extractVariables(serverId, templateId),
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        toast.error(`提取变量失败: ${detail || error.message}`);
      },
    });
  };

  const useConvertToTemplateMode = () => {
    return useMutation({
      mutationFn: ({
        serverId,
        templateId,
        variableValues,
      }: {
        serverId: string;
        templateId: number;
        variableValues: Record<string, unknown>;
      }) => templateApi.convertToTemplateMode(serverId, templateId, variableValues),
      onSuccess: (data) => {
        if (data.task_id) {
          queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
        }
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (Array.isArray(detail)) {
          toast.error(`转换失败: ${detail.join(", ")}`);
        } else {
          toast.error(`转换失败: ${detail || error.message}`);
        }
      },
    });
  };

  return {
    useCreateTemplate,
    useUpdateTemplate,
    useDeleteTemplate,
    usePreviewRenderedYaml,
    useCheckConversion,
    useUpdateServerTemplateConfig,
    useUpdateDefaultVariables,
    useConvertToDirectMode,
    useExtractVariables,
    useConvertToTemplateMode,
  };
};
