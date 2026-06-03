import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import { AlertCircle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { useAuthMutations } from '@/hooks/mutations/useAuthMutations'
import { useCodeLoginWebsocket } from '@/hooks/useCodeLoginWebsocket'
import { useLoginPreferenceStore } from '@/stores/useLoginPreferenceStore'

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormData = z.infer<typeof loginSchema>

const Login = () => {
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

  const { control, handleSubmit } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: '', password: '' },
  })

  const handlePasswordLogin = (values: LoginFormData) => {
    loginMutation.mutate(values)
  }

  const handleSwitchLoginMethod = () => {
    setLoginPreference(loginPreference === 'password' ? 'code' : 'password')
  }

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(code)
      toast.success('复制成功')
    } catch {
      toast.error('复制失败')
    }
  }

  useEffect(() => {
    if (loginPreference === 'code') {
      connect()
      return () => { disconnect() }
    } else {
      disconnect()
    }
  }, [loginPreference, connect, disconnect])

  const progressValue = codeTimeout > 0
    ? Math.max(0, Math.min(100, (countdown / codeTimeout) * 100))
    : 0

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-96">
        <Card className="shadow-lg">
          <CardContent className="pt-6">
            <div className="text-center mb-6">
              <h1 className="text-2xl font-bold">登录</h1>
            </div>

            {loginPreference === 'password' ? (
              <form onSubmit={handleSubmit(handlePasswordLogin)} className="space-y-4">
                <Controller
                  name="username"
                  control={control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor={field.name}>用户名</FieldLabel>
                      <Input
                        {...field}
                        id={field.name}
                        placeholder="请输入用户名"
                        disabled={loginMutation.isPending}
                        aria-invalid={fieldState.invalid}
                      />
                      {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                    </Field>
                  )}
                />

                <Controller
                  name="password"
                  control={control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor={field.name}>密码</FieldLabel>
                      <Input
                        {...field}
                        id={field.name}
                        type="password"
                        placeholder="请输入密码"
                        disabled={loginMutation.isPending}
                        aria-invalid={fieldState.invalid}
                      />
                      {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                    </Field>
                  )}
                />

                {loginMutation.isError && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      {loginMutation.error?.message || '登录失败'}
                    </AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-4">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleSwitchLoginMethod}
                    className="flex-1"
                    disabled={loginMutation.isPending}
                  >
                    机器人登录
                  </Button>
                  <Button
                    type="submit"
                    disabled={loginMutation.isPending}
                    className="flex-1"
                  >
                    {loginMutation.isPending && <Spinner className="mr-2 size-4" />}
                    登录
                  </Button>
                </div>
              </form>
            ) : (
              <div className="space-y-4">
                <Field>
                  <FieldLabel>动态码</FieldLabel>
                  <div className="text-center">
                    <div className="text-2xl font-mono mb-2">{code}</div>
                    <div className="mb-2">
                      <Progress value={progressValue} />
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {connected
                        ? (countdown > 0 ? `${countdown}秒后过期` : '验证码已过期')
                        : (isConnecting ? '连接中...' : (codeError ? '连接失败' : '连接中...'))}
                    </p>
                  </div>
                </Field>

                {codeError && !isConnecting && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{codeError}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-4">
                  <Button
                    variant="outline"
                    onClick={handleSwitchLoginMethod}
                    className="flex-1"
                  >
                    密码登录
                  </Button>
                  <Button
                    onClick={handleCopyCode}
                    disabled={!connected || countdown === 0}
                    className="flex-1"
                  >
                    复制
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default Login
