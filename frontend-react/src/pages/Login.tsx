import React, { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Progress, App } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useLoginApi } from '@/hooks/useLoginApi'
import { useCodeLoginApi } from '@/hooks/useCodeLoginApi'
import { useLoginPreferenceStore } from '@/stores/useLoginPreferenceStore'
import { useHasToken } from '@/stores/useTokenStore'

const Login: React.FC = () => {
  const navigate = useNavigate()
  const hasToken = useHasToken()
  const { message } = App.useApp()
  const { loginPreference, setLoginPreference } = useLoginPreferenceStore()
  const { login, loading, error } = useLoginApi()
  
  const {
    code,
    timeout,
    countdown,
    success,
    connected,
    connect,
    disconnect,
  } = useCodeLoginApi()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const handlePasswordLogin = async () => {
    await login(username, password)
    // Don't navigate here - let the useEffect handle it
  }

  // Add effect to handle navigation when token changes
  useEffect(() => {
    if (hasToken) {
      message.success('登录成功')
      navigate('/')
    }
  }, [hasToken, navigate])

  const handleSwitchLoginMethod = () => {
    const newPreference = loginPreference === 'password' ? 'code' : 'password'
    setLoginPreference(newPreference)
    
    if (newPreference === 'code') {
      connect()
    } else {
      disconnect()
    }
  }

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(code)
      message.success('复制成功')
    } catch (error) {
      message.error('复制失败')
    }
  }

  useEffect(() => {
    if (loginPreference === 'code') {
      connect()
    } else {
      disconnect()
    }
    
    return () => {
      disconnect()
    }
  }, [loginPreference])

  useEffect(() => {
    if (success) {
      message.success('登录成功')
      navigate('/')
    }
  }, [success, navigate])

  useEffect(() => {
    if (error) {
      message.error(error)
    }
  }, [error])

  // Redirect if already logged in - do this after all hooks are called
  if (hasToken) {
    return null // or a loading spinner
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-96">
        <Card className="shadow-lg">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold">登录</h1>
          </div>

          {loginPreference === 'password' ? (
            <Form layout="vertical" onFinish={handlePasswordLogin}>
              <Form.Item label="用户名" required>
                <Input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="请输入用户名"
                />
              </Form.Item>
              
              <Form.Item label="密码" required>
                <Input.Password
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入密码"
                />
              </Form.Item>
              
              <Form.Item>
                <div className="flex gap-4">
                  <Button 
                    onClick={handleSwitchLoginMethod}
                    className="flex-1"
                  >
                    机器人登录
                  </Button>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    className="flex-1"
                  >
                    登录
                  </Button>
                </div>
              </Form.Item>
            </Form>
          ) : (
            <Form layout="vertical">
              <Form.Item label="动态码">
                <div className="text-center">
                  <div className="text-2xl font-mono mb-2">{code}</div>
                  <Progress
                    percent={(countdown / timeout) * 100}
                    showInfo={false}
                    strokeWidth={4}
                    className="mb-4"
                  />
                  <div className="text-sm text-gray-500 mb-4">
                    {connected ? `${countdown}秒后过期` : '连接中...'}
                  </div>
                </div>
              </Form.Item>
              
              <Form.Item>
                <div className="flex gap-4">
                  <Button 
                    onClick={handleSwitchLoginMethod}
                    className="flex-1"
                  >
                    密码登录
                  </Button>
                  <Button
                    type="primary"
                    onClick={handleCopyCode}
                    className="flex-1"
                  >
                    复制
                  </Button>
                </div>
              </Form.Item>
            </Form>
          )}
        </Card>
      </div>
    </div>
  )
}

export default Login
