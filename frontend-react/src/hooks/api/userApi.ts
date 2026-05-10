import type { User, UserCreate } from "@/types/User";
import { api } from "@/utils/api";

export const getCurrentUser = async (): Promise<User> => {
  const response = await api.get("/user/me");
  return response.data;
};

// OWNER-only endpoints below.
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
