import React from 'react'
import { Spin } from 'antd'

interface LoadingSpinnerProps {
  size?: 'small' | 'default' | 'large'
  tip?: string
  className?: string
  fullscreen?: boolean
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'large',
  tip = '加载中...',
  className = '',
  fullscreen = false
}) => {
  const containerClass = fullscreen 
    ? `flex items-center justify-center h-screen ${className}`
    : `flex items-center justify-center min-h-[400px] ${className}`
  
  return (
    <div className={containerClass}>
      <Spin size={size} tip={tip}>
        <div className="min-h-[100px] min-w-[100px]" />
      </Spin>
    </div>
  )
}

export default LoadingSpinner
