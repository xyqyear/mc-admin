import { archiveApi, type ArchiveFileContent, type ArchiveFileListResponse } from "@/hooks/api/archiveApi"
import { queryKeys } from "@/utils/api"
import { useQuery, type UseQueryOptions } from "@tanstack/react-query"

export const useArchiveQueries = () => {
  // Get archive files list
  const useArchiveFileList = (
    path: string = '/',
    enabled: boolean = true,
    options?: Omit<UseQueryOptions<ArchiveFileListResponse>, 'queryKey' | 'queryFn'>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.files(path),
      queryFn: () => archiveApi.getArchiveFiles(path),
      enabled: enabled, // 默认启用，但允许外部传入enabled=false
      staleTime: 30 * 1000, // 30 seconds - archive files change less frequently than server files
      refetchInterval: false, // Manual refresh pattern
      ...options,
    })
  }

  // Get archive file content
  const useArchiveFileContent = (
    path: string | null,
    options?: Omit<UseQueryOptions<ArchiveFileContent>, 'queryKey' | 'queryFn'>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.content(path || ''),
      queryFn: () => archiveApi.getArchiveFileContent(path!),
      enabled: !!path, // 默认启用，但允许外部传入enabled=false
      staleTime: 10 * 1000, // 10 seconds - content may change during editing
      refetchInterval: false,
      ...options,
    })
  }

  return {
    useArchiveFileList,
    useArchiveFileContent,
  }
}