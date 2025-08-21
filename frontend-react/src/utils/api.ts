import { useTokenStore } from '@/stores/useTokenStore'
import axios, { AxiosError, AxiosResponse } from 'axios'

// Types for better error handling
export interface ApiError {
  message: string
  status?: number
  code?: string
}

export interface ApiResponse<T = any> {
  data: T
  message?: string
  success: boolean
}

// Create axios instance with better defaults
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5678/api',
  timeout: 30000, // Increased timeout for larger operations
  headers: {
    'Content-Type': 'application/json',
  },
})

// Token management with better error handling
const getAuthToken = () => {
  try {
    return useTokenStore.getState().token
  } catch (error) {
    console.error('Failed to get auth token:', error)
    return null
  }
}

// Request interceptor with improved auth handling
api.interceptors.request.use(
  (config) => {
    const token = getAuthToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => {
    console.error('Request interceptor error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor with comprehensive error handling
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error.response?.status
    
    // Handle different error types
    if (status === 401) {
      // Clear token and let the app handle redirect through router
      try {
        useTokenStore.getState().clearToken()
      } catch (e) {
        console.error('Failed to clear token:', e)
      }
    }
    
    // Create standardized error object
    const apiError: ApiError = {
      message: (error.response?.data as any)?.message || error.message || 'Network error',
      status,
      code: error.code,
    }
    
    return Promise.reject(apiError)
  }
)

// Utility function for sleep (useful for demos/testing)
export const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms))

// Query key factory for consistent cache keys
export const queryKeys = {
  all: ['api'] as const,
  servers: () => [...queryKeys.all, 'servers'] as const,
  server: (id: string) => [...queryKeys.servers(), id] as const,
  serverPlayers: (id: string) => [...queryKeys.server(id), 'players'] as const,
  serverFiles: (id: string) => [...queryKeys.server(id), 'files'] as const,
  overview: () => [...queryKeys.all, 'overview'] as const,
  backups: () => [...queryKeys.all, 'backups'] as const,
} as const

export default api
