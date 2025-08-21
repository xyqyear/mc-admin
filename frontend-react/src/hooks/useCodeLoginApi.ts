import { useTokenStore } from '@/stores/useTokenStore'
import { App } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface CodeMessage {
  type: 'code'
  code: string
  timeout: number
}

interface VerifiedMessage {
  type: 'verified'
  access_token: string
}

type ServerMessage = CodeMessage | VerifiedMessage

export const useCodeLoginApi = () => {
  const [code, setCode] = useState('加载中')
  const [timeout, setTimeout] = useState(60)
  const [countdown, setCountdown] = useState(0)
  const [success, setSuccess] = useState(false)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  
  const wsRef = useRef<WebSocket | null>(null)
  const countdownRef = useRef<NodeJS.Timeout | null>(null)
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { setToken } = useTokenStore()
  const { message } = App.useApp()
  const navigate = useNavigate()

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5678/api'
  const wsBaseUrl = apiBaseUrl
    .replace('https', 'wss')
    .replace('http', 'ws')
    .replace(/\/$/, '')

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000) // Normal closure
      wsRef.current = null
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current)
      countdownRef.current = null
    }
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current)
      errorTimeoutRef.current = null
    }
    setConnected(false)
    setIsConnecting(false)
    setError(null) // 清除错误状态
    setCode('加载中') // 重置code，像新访问一样
    setCountdown(0)
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // 重置状态，像新访问一样
    setError(null)
    setCode('连接中...')
    setConnected(false)
    setIsConnecting(true)
    
    // 清除之前的错误超时
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current)
      errorTimeoutRef.current = null
    }
    
    try {
      wsRef.current = new WebSocket(`${wsBaseUrl}/auth/code`)
      
      wsRef.current.onopen = () => {
        setConnected(true)
        setIsConnecting(false)
        setError(null)
        // 清除错误超时，因为连接成功了
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
          errorTimeoutRef.current = null
        }
      }

      wsRef.current.onmessage = (event) => {
        if (event.data === 'pong') return
        
        try {
          const data: ServerMessage = JSON.parse(event.data)
          if (data.type === 'code') {
            setCode(data.code)
            setTimeout(data.timeout)
            setCountdown(data.timeout)
          } else if (data.type === 'verified') {
            setSuccess(true)
            setToken(data.access_token)
            message.success('验证成功，正在跳转...')
            disconnect()
            navigate('/')
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
          setError('消息解析失败')
        }
      }

      wsRef.current.onclose = (event) => {
        setConnected(false)
        setIsConnecting(false)
        // 只有在异常关闭且已经连接过的情况下才显示错误
        if (event.code !== 1000 && event.code !== 1001 && event.code !== 1006) {
          // 延迟显示错误，避免初始连接失败时立即显示
          errorTimeoutRef.current = window.setTimeout(() => {
            setError('连接已断开')
          }, 1000) as unknown as ReturnType<typeof setTimeout>
        }
      }

      wsRef.current.onerror = () => {
        setConnected(false)
        setIsConnecting(false)
        // 延迟显示错误，给连接一些时间
        errorTimeoutRef.current = window.setTimeout(() => {
          setError('连接失败，请检查网络')
        }, 2000) as unknown as ReturnType<typeof setTimeout>
      }
    } catch (err) {
      console.error('WebSocket connection failed:', err)
      setIsConnecting(false)
      setError('无法建立连接')
    }
  }, [wsBaseUrl, setToken, message, navigate, disconnect])

  // Countdown effect
  useEffect(() => {
    if (connected && countdown > 0) {
      countdownRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (countdownRef.current) {
              clearInterval(countdownRef.current)
              countdownRef.current = null
            }
            setError('验证码已过期，请重新获取')
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current)
      }
    }
  }, [connected, countdown])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect()
    }
  }, [disconnect])

  return {
    code,
    timeout,
    countdown,
    success,
    connected,
    isConnecting,
    error,
    connect,
    disconnect,
  }
}
