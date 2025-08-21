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
  
  const wsRef = useRef<WebSocket | null>(null)
  const countdownRef = useRef<NodeJS.Timeout | null>(null)
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
      wsRef.current.close()
      wsRef.current = null
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current)
      countdownRef.current = null
    }
    setConnected(false)
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setError(null)
    
    try {
      wsRef.current = new WebSocket(`${wsBaseUrl}/auth/code`)
      
      wsRef.current.onopen = () => {
        setConnected(true)
        setError(null)
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
        if (event.code !== 1000) { // Not a normal closure
          setError('连接已断开')
        }
      }

      wsRef.current.onerror = () => {
        setConnected(false)
        setError('连接失败，请检查网络')
      }
    } catch (err) {
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
    error,
    connect,
    disconnect,
  }
}
