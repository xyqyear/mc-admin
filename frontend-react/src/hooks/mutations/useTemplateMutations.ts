import { useMutation, useQueryClient } from "@tanstack/react-query";
import { message } from "antd";
import { queryKeys } from "@/utils/api";
import {
  templateApi,
  TemplateCreateRequest,
  TemplateUpdateRequest,
  VariableDefinition,
} from "@/hooks/api/templateApi";

export const useTemplateMutations = () => {
  const queryClient = useQueryClient();

  // Create template
  const useCreateTemplate = () => {
    return useMutation({
      mutationFn: (request: TemplateCreateRequest) =>
        templateApi.createTemplate(request),
      onSuccess: () => {
        message.success("模板创建成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.list(),
        });
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          message.error(`创建失败: ${detail.errors.join(", ")}`);
        } else {
          message.error(`创建失败: ${detail || error.message}`);
        }
      },
    });
  };

  // Update template
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
        message.success("模板更新成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.list(),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.detail(id),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.schema(id),
        });
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          message.error(`更新失败: ${detail.errors.join(", ")}`);
        } else {
          message.error(`更新失败: ${detail || error.message}`);
        }
      },
    });
  };

  // Delete template
  const useDeleteTemplate = () => {
    return useMutation({
      mutationFn: (id: number) => templateApi.deleteTemplate(id),
      onSuccess: () => {
        message.success("模板删除成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.list(),
        });
      },
      onError: (error: any) => {
        message.error(`删除失败: ${error.response?.data?.detail || error.message}`);
      },
    });
  };

  // Preview rendered YAML
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
          message.error(`预览失败: ${detail.errors.join(", ")}`);
        } else {
          message.error(`预览失败: ${detail || error.message}`);
        }
      },
    });
  };

  // Update server template config
  const useUpdateServerTemplateConfig = () => {
    return useMutation({
      mutationFn: ({
        serverId,
        variableValues,
      }: {
        serverId: string;
        variableValues: Record<string, unknown>;
      }) => templateApi.updateServerTemplateConfig(serverId, variableValues),
      onSuccess: (_, { serverId }) => {
        message.success("配置更新成功");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.serverConfig(serverId),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.compose.file(serverId),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.serverInfos.detail(serverId),
        });
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        if (typeof detail === "object" && detail.errors) {
          message.error(`更新失败: ${detail.errors.join(", ")}`);
        } else {
          message.error(`更新失败: ${detail || error.message}`);
        }
      },
    });
  };

  // Update default variables
  const useUpdateDefaultVariables = () => {
    return useMutation({
      mutationFn: (variables: VariableDefinition[]) =>
        templateApi.updateDefaultVariables(variables),
      onSuccess: () => {
        message.success("默认变量配置已更新");
        queryClient.invalidateQueries({
          queryKey: queryKeys.templates.defaultVariables(),
        });
      },
      onError: (error: any) => {
        const detail = error.response?.data?.detail;
        message.error(`更新失败: ${detail || error.message}`);
      },
    });
  };

  return {
    useCreateTemplate,
    useUpdateTemplate,
    useDeleteTemplate,
    usePreviewRenderedYaml,
    useUpdateServerTemplateConfig,
    useUpdateDefaultVariables,
  };
};
