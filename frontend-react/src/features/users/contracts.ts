import type { components } from './generated/api'

export type User = components['schemas']['UserPublic']
export type UserCreate = components['schemas']['UserCreate']
export type LoginResponse = components['schemas']['LoginResponse']
export type UserRole = components['schemas']['UserRole']
export const UserRole = { ADMIN: 'admin', OWNER: 'owner' } as const satisfies Record<string, UserRole>

export interface LoginRequest {
  username: string;
  password: string;
}

export interface CompleteCodeLoginRequest {
  ticket: string;
}
