import { archiveApi } from "@/features/archives/api";
import type { ArchiveFileListResponse } from '@/features/archives/contracts';
import { queryKeys } from "@/shared/http/api"
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
