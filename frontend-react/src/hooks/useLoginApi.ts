import { useTokenStore } from '@/stores/useTokenStore'
import { api, ApiError } from '@/utils/api'
import { useMutation } from '@tanstack/react-query'
import { App } from 'antd'
import { useNavigate } from 'react-router-dom'

interface LoginRequest {
  username: string
  password: string
}

interface LoginResponse {
  access_token: string
  token_type: 'bearer'
}

// Login API function
const loginApi = async ({ username, password }: LoginRequest): Promise<LoginResponse> => {
  const formData = new FormData()
  formData.append('grant_type', 'password')
  formData.append('username', username)
  formData.append('password', password)

  const response = await api.post<LoginResponse>('/auth/token', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  
  return response.data
}

// Modern hook using TanStack Query
export const useLoginMutation = () => {
  const { setToken } = useTokenStore()
  const navigate = useNavigate()
  const { message } = App.useApp()
  
  return useMutation({
    mutationFn: loginApi,
    onSuccess: (data) => {
      setToken(data.access_token)
      message.success('登录成功')
      navigate('/')
    },
    onError: (error: ApiError) => {
      const errorMessage = error.message || '登录失败，请检查用户名和密码'
      message.error(errorMessage)
    },
  })
}
