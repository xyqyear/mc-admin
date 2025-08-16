import { useTokenStore } from '@/stores/useTokenStore'
import { api } from '@/utils/api'
import { useState } from 'react'

interface LoginResponse {
  access_token: string
  token_type: 'bearer'
}

export const useLoginApi = () => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setToken } = useTokenStore()

  const login = async (username: string, password: string) => {
    setLoading(true)
    setError(null)
    
    try {
      const formData = new FormData()
      formData.append('grant_type', 'password')
      formData.append('username', username)
      formData.append('password', password)

      const response = await api.post<LoginResponse>('/auth/token', formData)
      setToken(response.data.access_token)
      return true
    } catch (err: any) {
      setError(err.response?.data?.detail || '登录失败')
      return false
    } finally {
      setLoading(false)
    }
  }

  return { login, loading, error }
}
