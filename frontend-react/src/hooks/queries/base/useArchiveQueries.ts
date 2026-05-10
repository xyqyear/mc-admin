import { archiveApi, type ArchiveFileListResponse } from "@/hooks/api/archiveApi"
import { queryKeys } from "@/utils/api"
import { useQuery, type UseQueryOptions } from "@tanstack/react-query"

export const useArchiveQueries = () => {
  const useArchiveFileList = (
    path: string = '/',
    enabled: boolean = true,
    options?: Omit<UseQueryOptions<ArchiveFileListResponse>, 'queryKey' | 'queryFn'>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.files(path),
      queryFn: () => archiveApi.getArchiveFiles(path),
      enabled: enabled,
      // Archive files change less frequently than server files.
      staleTime: 30 * 1000,
      refetchInterval: false,
      ...options,
    })
  }

  const useArchiveSHA256 = (
    path: string | null,
    enabled: boolean = false,
    options?: Omit<UseQueryOptions<{ sha256: string }>, 'queryKey' | 'queryFn' | 'enabled'>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.sha256(path || ''),
      queryFn: () => archiveApi.calculateSHA256(path!),
      // Default disabled — SHA256 is expensive and triggered explicitly.
      enabled: !!path && enabled,
      // Hash is content-derived; cache forever for a given path until invalidated on write.
      staleTime: Infinity,
      refetchInterval: false,
      ...options,
    })
  }

  return {
    useArchiveFileList,
    useArchiveSHA256,
  }
}
