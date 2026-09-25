import { shouldRetryQuery } from '@/shared/http/api'
import * as userApi from "@/features/users/api";
import { queryKeys } from "@/shared/http/api";
import { useQuery } from "@tanstack/react-query";

export const useCurrentUser = () => {
  return useQuery({
    queryKey: queryKeys.user.me(),
    queryFn: userApi.getCurrentUser,
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 3),
  });
};

export const useAllUsers = () => {
  return useQuery({
    queryKey: queryKeys.admin.users(),
    queryFn: userApi.getAllUsers,
    staleTime: 2 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 3),
  });
};
