import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/utils/api";
import { templateApi } from "@/hooks/api/templateApi";

export const useTemplates = () => {
  return useQuery({
    queryKey: queryKeys.templates.list(),
    queryFn: templateApi.getTemplates,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
};

export const useTemplate = (id: number | null) => {
  return useQuery({
    queryKey: queryKeys.templates.detail(id!),
    queryFn: () => templateApi.getTemplate(id!),
    enabled: id !== null,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
};

export const useTemplateSchema = (id: number | null) => {
  return useQuery({
    queryKey: queryKeys.templates.schema(id!),
    queryFn: () => templateApi.getTemplateSchema(id!),
    enabled: id !== null,
    // Schemas rarely change.
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
};

export const useAvailablePorts = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.templates.availablePorts(),
    queryFn: templateApi.getAvailablePorts,
    enabled,
    // Ports can change as other servers are created/destroyed; refetch on focus.
    staleTime: 30 * 1000,
    refetchOnWindowFocus: true,
  });
};

export const useServerTemplatePreview = (serverId: string | null) => {
  return useQuery({
    queryKey: queryKeys.templates.serverConfigPreview(serverId!),
    queryFn: () => templateApi.getServerTemplatePreview(serverId!),
    enabled: !!serverId,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
};

export const useServerTemplateConfig = (serverId: string | null) => {
  return useQuery({
    queryKey: queryKeys.templates.serverConfig(serverId!),
    queryFn: () => templateApi.getServerTemplateConfig(serverId!),
    enabled: !!serverId,
    staleTime: 2 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
};

export const useDefaultVariables = () => {
  return useQuery({
    queryKey: queryKeys.templates.defaultVariables(),
    queryFn: templateApi.getDefaultVariables,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
};
