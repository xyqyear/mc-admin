export enum UserRole {
  ADMIN = "admin",
  OWNER = "owner",
}

export interface User {
  id: number;
  username: string;
  role: UserRole;
  created_at: string;
}

export interface UserCreate {
  username: string;
  password: string;
  role: UserRole;
}
