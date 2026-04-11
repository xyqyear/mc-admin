import { authApi, type LoginRequest } from "@/hooks/api/authApi";
import { useTokenStore } from "@/stores/useTokenStore";
import type { ApiError } from "@/utils/api";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

export const useAuthMutations = () => {
  const { setToken } = useTokenStore();
  const navigate = useNavigate();

  // Traditional password-based login mutation
  const useLogin = () => {
    return useMutation({
      mutationFn: (credentials: LoginRequest) => authApi.login(credentials),
      onSuccess: (data) => {
        setToken(data.access_token);
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