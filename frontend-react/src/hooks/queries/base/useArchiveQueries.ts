import { useQuery, type UseQueryOptions } from "@tanstack/react-query"
import { archiveApi, type ArchiveFileListResponse, type ArchiveFileContent } from "@/hooks/api/archiveApi"
import { queryKeys } from "@/utils/api"

export const useArchiveQueries = () => {
  // Get archive files list
  const useArchiveFileList = (
    path: string = '/',
    options?: UseQueryOptions<ArchiveFileListResponse>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.files(path),
      queryFn: () => archiveApi.getArchiveFiles(path),
      staleTime: 30 * 1000, // 30 seconds - archive files change less frequently than server files
      refetchInterval: false, // Manual refresh pattern
      ...options,
    })
  }

  // Get archive file content
  const useArchiveFileContent = (
    path: string | null,
    options?: UseQueryOptions<ArchiveFileContent>
  ) => {
    return useQuery({
      queryKey: queryKeys.archive.content(path || ''),
      queryFn: () => archiveApi.getArchiveFileContent(path!),
      enabled: !!path,
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