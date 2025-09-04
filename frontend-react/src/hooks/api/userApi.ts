import { api } from "@/utils/api";
import type { User, UserCreate } from "@/types/User";

// Get current user info
export const getCurrentUser = async (): Promise<User> => {
  const response = await api.get("/user/me");
  return response.data;
};

// Admin endpoints - require OWNER role
export const getAllUsers = async (): Promise<User[]> => {
  const response = await api.get("/admin/users");
  return response.data;
};

export const createUser = async (userData: UserCreate): Promise<User> => {
  const response = await api.post("/admin/users", userData);
  return response.data;
};

export const deleteUser = async (userId: number): Promise<void> => {
  await api.delete(`/admin/users/${userId}`);
};