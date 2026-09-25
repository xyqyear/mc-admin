import { api } from "@/shared/http/api";
import type { LoginRequest, LoginResponse, CompleteCodeLoginRequest } from '@/features/users/contracts';


export const authApi = {
  login: async (credentials: LoginRequest): Promise<LoginResponse> => {
    const formData = new FormData();
    formData.append("grant_type", "password");
    formData.append("username", credentials.username);
    formData.append("password", credentials.password);

    const response = await api.post<LoginResponse>("/auth/token", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });

    return response.data;
  },

  completeCodeLogin: async (
    request: CompleteCodeLoginRequest,
  ): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>("/auth/code/complete", request);
    return response.data;
  },

  logout: async (): Promise<void> => {
    await api.post("/auth/logout");
  },
};