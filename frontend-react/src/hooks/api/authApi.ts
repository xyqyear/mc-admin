import { api } from "@/utils/api";

// Request and response types
interface LoginRequest {
  username: string;
  password: string;
}

interface LoginResponse {
  access_token: string;
  token_type: "bearer";
}

export const authApi = {
  // Traditional password-based login
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
};

// Export types for use in other modules
export type { LoginRequest, LoginResponse };