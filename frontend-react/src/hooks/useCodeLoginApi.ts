import { useTokenStore } from '@/stores/useTokenStore'
import { useEffect, useRef, useState } from 'react'

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
  
  const wsRef = useRef<WebSocket | null>(null)
  const countdownRef = useRef<NodeJS.Timeout | null>(null)
  const { setToken } = useTokenStore()

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5678/api'
  const wsBaseUrl = apiBaseUrl
    .replace('https', 'wss')
    .replace('http', 'ws')
    .replace(/\/$/, '')

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    wsRef.current = new WebSocket(`${wsBaseUrl}/auth/code`)
    
    wsRef.current.onopen = () => {
      setConnected(true)
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
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    wsRef.current.onclose = () => {
      setConnected(false)
    }

    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error)
      setConnected(false)
    }
  }

  const disconnect = () => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current)
      countdownRef.current = null
    }
    setConnected(false)
  }

  useEffect(() => {
    if (connected && countdown > 0) {
      countdownRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (countdownRef.current) {
              clearInterval(countdownRef.current)
              countdownRef.current = null
            }
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

  useEffect(() => {
    return () => {
      disconnect()
    }
  }, [])

  return {
    code,
    timeout,
    countdown,
    success,
    connected,
    connect,
    disconnect,
  }
}
