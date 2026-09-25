import { authApi } from "@/features/users/auth";
import type { LoginRequest } from '@/features/users/contracts';
import type { ApiError } from "@/shared/http/api";
import { queryKeys } from "@/shared/http/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from 'react-router';
import { toast } from "sonner";

export const useAuthMutations = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const useLogin = () => {
    return useMutation({
      mutationFn: (credentials: LoginRequest) => authApi.login(credentials),
      onSuccess: (data) => {
        queryClient.setQueryData(queryKeys.user.me(), data.user);
        toast.success("登录成功");
        navigate("/");
      },
      onError: (error: ApiError) => {
        const errorMessage = error.message || "登录失败，请检查用户名和密码";
        toast.error(errorMessage);
      },
    });
  };

  return {
    useLogin,
  };
};
