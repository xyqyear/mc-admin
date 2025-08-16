import { useTokenStore } from '@/stores/useTokenStore'
import { message } from 'antd'
import axios from 'axios'

// Create axios instance
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5678/api',
  timeout: 10000,
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = useTokenStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useTokenStore.getState().clearToken()
      message.error('登录过期，请重新登录')
      window.location.href = '/login'
    } else if (error.response?.status === 403) {
      message.error('权限不足')
    } else if (error.response?.status >= 500) {
      message.error('服务器错误，请稍后重试')
    }
    return Promise.reject(error)
  }
)

export const sleep = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms))
