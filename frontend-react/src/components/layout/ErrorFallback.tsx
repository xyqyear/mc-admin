import React from 'react'
import { Button, Result } from 'antd'
import { FallbackProps } from 'react-error-boundary'


export const ErrorFallback: React.FC<FallbackProps> = ({ error, resetErrorBoundary }) => {
  const errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred'

  return (
    <div className="flex items-center justify-center min-h-screen">
      <Result
        status="error"
        title="Something went wrong"
        subTitle={errorMessage}
        extra={[
          <Button type="primary" onClick={resetErrorBoundary} key="retry">
            Try Again
          </Button>,
          <Button key="home" onClick={() => window.location.href = '/'}>
            Go Home
          </Button>,
        ]}
      />
    </div>
  )
}

export default ErrorFallback
