import { AlertCircle } from 'lucide-react'
import type { FallbackProps } from 'react-error-boundary'
import { Button } from '@/shared/ui/button'
import { ButtonLink } from '@/shared/components/ButtonLink'
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'

export const ErrorFallback = ({ error, resetErrorBoundary }: FallbackProps) => {
  const errorMessage = error instanceof Error ? error.message : '发生了意外错误'

  return (
    <div className="flex items-center justify-center min-h-screen p-8">
      <div className="max-w-md w-full space-y-4">
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>出错了</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
        <div className="flex gap-2">
          <Button onClick={resetErrorBoundary} className="flex-1">
            重试
          </Button>
          <ButtonLink variant="outline" to="/" reloadDocument className="flex-1">
            返回首页
          </ButtonLink>
        </div>
      </div>
    </div>
  )
}

export default ErrorFallback
