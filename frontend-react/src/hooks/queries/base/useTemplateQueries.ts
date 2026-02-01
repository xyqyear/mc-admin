import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/utils/api";
import { templateApi } from "@/hooks/api/templateApi";

/**
 * Hook to get all templates
 */
export const useTemplates = () => {
  return useQuery({
    queryKey: queryKeys.templates.list(),
    queryFn: templateApi.getTemplates,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
};

/**
 * Hook to get a specific template
 */
export const useTemplate = (id: number | null) => {
  return useQuery({
    queryKey: queryKeys.templates.detail(id!),
    queryFn: () => templateApi.getTemplate(id!),
    enabled: id !== null,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
};

/**
 * Hook to get JSON Schema for a template
 */
export const useTemplateSchema = (id: number | null) => {
  return useQuery({
    queryKey: queryKeys.templates.schema(id!),
    queryFn: () => templateApi.getTemplateSchema(id!),
    enabled: id !== null,
    staleTime: 10 * 60 * 1000, // 10 minutes - schemas rarely change
    refetchOnWindowFocus: false,
  });
};

/**
 * Hook to get available ports for new server
 */
export const useAvailablePorts = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.templates.availablePorts(),
    queryFn: templateApi.getAvailablePorts,
    enabled,
    staleTime: 30 * 1000, // 30 seconds - ports can change
    refetchOnWindowFocus: true,
  });
};

/**
 * Hook to check if a server is template-based
 */
export const useServerTemplatePreview = (serverId: string | null) => {
  return useQuery({
    queryKey: queryKeys.templates.serverConfigPreview(serverId!),
    queryFn: () => templateApi.getServerTemplatePreview(serverId!),
    enabled: !!serverId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
};

/**
 * Hook to get template config for a template-created server
 */
export const useServerTemplateConfig = (serverId: string | null) => {
  return useQuery({
    queryKey: queryKeys.templates.serverConfig(serverId!),
    queryFn: () => templateApi.getServerTemplateConfig(serverId!),
    enabled: !!serverId,
    staleTime: 2 * 60 * 1000, // 2 minutes
    refetchOnWindowFocus: false,
  });
};
