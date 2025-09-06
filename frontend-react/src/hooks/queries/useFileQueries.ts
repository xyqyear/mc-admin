import { queryKeys } from "@/utils/api";
import { useQuery } from "@tanstack/react-query";
import { fileApi } from "../api/fileApi";

export const useFileList = (
  serverId: string | undefined,
  path: string = "/"
) => {
  return useQuery({
    queryKey: [...queryKeys.files.list(serverId || "", path)],
    queryFn: () => fileApi.listFiles(serverId!, path),
    enabled: !!serverId,
    staleTime: 1000 * 30, // 30 seconds
    refetchOnWindowFocus: true,
  });
};

export const useFileContent = (
  serverId: string | undefined,
  path: string | null
) => {
  return useQuery({
    queryKey: [...queryKeys.files.content(serverId || "", path || "")],
    queryFn: () => fileApi.getFileContent(serverId!, path!),
    enabled: !!serverId && !!path,
    staleTime: 1000 * 60, // 1 minute
  });
};

