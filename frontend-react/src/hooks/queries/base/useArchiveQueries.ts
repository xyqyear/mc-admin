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

  return {
    useArchiveFileList,
  }
}
