import * as userApi from "@/hooks/api/userApi";
import { queryKeys } from "@/utils/api";
import { useQuery } from "@tanstack/react-query";

export const useCurrentUser = () => {
  return useQuery({
    queryKey: queryKeys.user.me(),
    queryFn: userApi.getCurrentUser,
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error: any) => {
      if (error?.response?.status === 401 || error?.response?.status === 403) {
        return false;
      }
      return failureCount < 3;
    },
  });
};

export const useAllUsers = () => {
  return useQuery({
    queryKey: queryKeys.admin.users(),
    queryFn: userApi.getAllUsers,
    staleTime: 2 * 60 * 1000,
    retry: (failureCount, error: any) => {
      if (error?.response?.status === 401 || error?.response?.status === 403) {
        return false;
      }
      return failureCount < 3;
    },
  });
};
