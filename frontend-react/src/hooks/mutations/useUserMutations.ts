import * as userApi from "@/hooks/api/userApi";
import type { UserCreate } from "@/types/User";
import { queryKeys } from "@/utils/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { message } from "antd";

export const useCreateUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userData: UserCreate) => userApi.createUser(userData),
    onSuccess: (data) => {
      // Invalidate and refetch users list
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users() });
      message.success(`用户 ${data.username} 创建成功`);
    },
    onError: (error: any) => {
      const errorMsg = error?.message || "创建用户失败";
      message.error(errorMsg);
    },
  });
};

export const useDeleteUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: number) => userApi.deleteUser(userId),
    onSuccess: () => {
      // Invalidate and refetch users list
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users() });
      message.success("用户删除成功");
    },
    onError: (error: any) => {
      const errorMsg = error?.message || "删除用户失败";
      message.error(errorMsg);
    },
  });
};
