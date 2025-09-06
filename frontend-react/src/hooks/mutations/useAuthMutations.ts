import { authApi, type LoginRequest } from "@/hooks/api/authApi";
import { useTokenStore } from "@/stores/useTokenStore";
import type { ApiError } from "@/utils/api";
import { useMutation } from "@tanstack/react-query";
import { App } from "antd";
import { useNavigate } from "react-router-dom";

export const useAuthMutations = () => {
  const { setToken } = useTokenStore();
  const navigate = useNavigate();
  const { message } = App.useApp();

  // Traditional password-based login mutation
  const useLogin = () => {
    return useMutation({
      mutationFn: (credentials: LoginRequest) => authApi.login(credentials),
      onSuccess: (data) => {
        setToken(data.access_token);
        message.success("登录成功");
        navigate("/");
      },
      onError: (error: ApiError) => {
        const errorMessage = error.message || "登录失败，请检查用户名和密码";
        message.error(errorMessage);
      },
    });
  };

  return {
    useLogin,
  };
};