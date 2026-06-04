import { AlertCircle } from 'lucide-react'
import type { FallbackProps } from 'react-error-boundary'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export const ErrorFallback = ({ error, resetErrorBoundary }: FallbackProps) => {
  const errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred'

  return (
    <div className="flex items-center justify-center min-h-screen p-8">
      <div className="max-w-md w-full space-y-4">
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
        <div className="flex gap-2">
          <Button onClick={resetErrorBoundary} className="flex-1">
            Try Again
          </Button>
          <Button variant="outline" onClick={() => window.location.href = '/'} className="flex-1">
            Go Home
          </Button>
        </div>
      </div>
    </div>
  )
}

export default ErrorFallback
