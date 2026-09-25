import type { ApiError } from '@/shared/http/api'
import * as userApi from "@/features/users/api";
import type { UserCreate } from "@/features/users/contracts";
import { queryKeys } from "@/shared/http/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

export const useCreateUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userData: UserCreate) => userApi.createUser(userData),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users() });
      toast.success(`用户 ${data.username} 创建成功`);
    },
    onError: (error: ApiError) => {
      const errorMsg = error?.message || "创建用户失败";
      toast.error(errorMsg);
    },
  });
};

export const useDeleteUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: number) => userApi.deleteUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users() });
      toast.success("用户删除成功");
    },
    onError: (error: ApiError) => {
      const errorMsg = error?.message || "删除用户失败";
      toast.error(errorMsg);
    },
  });
};
