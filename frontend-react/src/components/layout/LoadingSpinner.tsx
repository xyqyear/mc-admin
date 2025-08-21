import React from 'react'
import { Spin } from 'antd'

interface LoadingSpinnerProps {
  size?: 'small' | 'default' | 'large'
  tip?: string
  className?: string
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'large',
  tip = 'Loading...',
  className = ''
}) => {
  return (
    <div className={`flex items-center justify-center h-screen ${className}`}>
      <Spin size={size} tip={tip} />
    </div>
  )
}

export default LoadingSpinner
