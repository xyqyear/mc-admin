import React from 'react'
import { Button, Result } from 'antd'
import { FallbackProps } from 'react-error-boundary'

export const ErrorFallback: React.FC<FallbackProps> = ({ error, resetErrorBoundary }) => {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <Result
        status="error"
        title="Something went wrong"
        subTitle={error.message || 'An unexpected error occurred'}
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
