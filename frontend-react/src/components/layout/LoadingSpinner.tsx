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
  tip = 'Loading...',
  className = '',
  fullscreen = false
}) => {
  const containerClass = fullscreen 
    ? `flex items-center justify-center h-screen ${className}`
    : `flex items-center justify-center min-h-[400px] ${className}`
  
  return (
    <div className={containerClass}>
      <Spin size={size} tip={tip} />
    </div>
  )
}

export default LoadingSpinner
