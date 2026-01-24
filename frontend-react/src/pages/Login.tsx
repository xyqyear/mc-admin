import React, { useEffect } from 'react'
import { Card, Form, Input, Button, App, Alert, Progress } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuthMutations } from '@/hooks/mutations/useAuthMutations'
import { useCodeLoginWebsocket } from '@/hooks/useCodeLoginWebsocket'
import { useLoginPreferenceStore } from '@/stores/useLoginPreferenceStore'
import { useIsAuthenticated } from '@/stores/useTokenStore'

const Login: React.FC = () => {
  const navigate = useNavigate()
  const isAuthenticated = useIsAuthenticated()
  const { message } = App.useApp()
  const { loginPreference, setLoginPreference } = useLoginPreferenceStore()
  const { useLogin } = useAuthMutations()
  const loginMutation = useLogin()

  const {
    code,
    countdown,
    codeTimeout,
    connected,
    isConnecting,
    error: codeError,
    connect,
    disconnect,
  } = useCodeLoginWebsocket()

  const [form] = Form.useForm()

  const handlePasswordLogin = async (values: { username: string; password: string }) => {
    loginMutation.mutate(values)
  }

  const handleSwitchLoginMethod = () => {
    const newPreference = loginPreference === 'password' ? 'code' : 'password'
    setLoginPreference(newPreference)
  }

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(code)
      message.success('复制成功')
    } catch {
      message.error('复制失败')
    }
  }

  useEffect(() => {
    if (loginPreference === 'code') {
      connect()
      return () => {
        disconnect()
      }
    } else {
      disconnect()
    }
  }, [loginPreference, connect, disconnect])

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

  if (isAuthenticated) {
    return null
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-96">
        <Card className="shadow-lg">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold">登录</h1>
          </div>

          {loginPreference === 'password' ? (
            <Form
              form={form}
              layout="vertical"
              onFinish={handlePasswordLogin}
              disabled={loginMutation.isPending}
            >
              <Form.Item
                label="用户名"
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
              >
                <Input placeholder="请输入用户名" />
              </Form.Item>

              <Form.Item
                label="密码"
                name="password"
                rules={[{ required: true, message: '请输入密码' }]}
              >
                <Input.Password placeholder="请输入密码" />
              </Form.Item>

              {loginMutation.isError && (
                <Form.Item>
                  <Alert
                    type="error"
                    title={loginMutation.error?.message || '登录失败'}
                    showIcon
                  />
                </Form.Item>
              )}

              <Form.Item>
                <div className="flex gap-4">
                  <Button
                    onClick={handleSwitchLoginMethod}
                    className="flex-1"
                    disabled={loginMutation.isPending}
                  >
                    机器人登录
                  </Button>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={loginMutation.isPending}
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
                  <div className="mb-2">
                    <Progress
                      percent={codeTimeout > 0 ? Math.max(0, Math.min(100, (countdown / codeTimeout) * 100)) : 0}
                      status={connected && countdown > 0 ? 'active' : (countdown === 0 ? 'exception' : (isConnecting ? 'normal' : 'exception'))}
                      showInfo={false}
                    />
                  </div>
                  <div className="text-sm text-gray-500 mb-4">
                    {connected ?
                      (countdown > 0 ? `${countdown}秒后过期` : '验证码已过期') :
                      (isConnecting ? '连接中...' : (codeError ? '连接失败' : '连接中...'))
                    }
                  </div>
                </div>
              </Form.Item>

              {codeError && !isConnecting && (
                <Form.Item>
                  <Alert type="error" title={codeError} showIcon />
                </Form.Item>
              )}

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
                    disabled={!connected || countdown === 0}
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
