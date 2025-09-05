import React from 'react'
import { Spin } from 'antd'

interface LoadingSpinnerProps {
  size?: 'small' | 'default' | 'large'
  tip?: string
  className?: string
  fullscreen?: boolean
  inline?: boolean
  height?: string | number
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'large',
  tip = '加载中...',
  className = '',
  fullscreen = false,
  inline = false,
  height
}) => {
  if (inline) {
    return <Spin size={size} className={className} />
  }

  const containerClass = fullscreen
    ? `flex items-center justify-center h-screen ${className}`
    : `flex items-center justify-center ${height ? '' : 'min-h-[400px]'} ${className}`

  const containerStyle = height ? { height } : {}

  return (
    <div className={containerClass} style={containerStyle}>
      <Spin size={size} tip={tip}>
        <div className="min-h-[100px] min-w-[100px]" />
      </Spin>
    </div>
  )
}

export default LoadingSpinner
