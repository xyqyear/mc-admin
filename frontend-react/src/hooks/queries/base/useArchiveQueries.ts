import { archiveApi, type ArchiveFileListResponse } from "@/hooks/api/archiveApi"
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

  // Calculate SHA256 hash
  const useArchiveSHA256 = (
    path: string | null,
    enabled: boolean = false,
    options?: Omit<UseQueryOptions<{ sha256: string }>, 'queryKey' | 'queryFn' | 'enabled'>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.sha256(path || ''),
      queryFn: () => archiveApi.calculateSHA256(path!),
      enabled: !!path && enabled, // 默认不启用，需要手动触发
      staleTime: Infinity, // SHA256 hash shouldn't change for the same file
      refetchInterval: false,
      ...options,
    })
  }

  return {
    useArchiveFileList,
    useArchiveSHA256,
  }
}
