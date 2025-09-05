import React from 'react'
import { Typography, Space, Tag } from 'antd'

const { Title } = Typography

interface PageHeaderProps {
  title: string
  icon?: React.ReactNode
  actions?: React.ReactNode
  serverTag?: string
  className?: string
}

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  icon,
  actions,
  serverTag,
  className = ''
}) => {
  return (
    <div className={`flex justify-between items-center ml-3 ${className}`}>
      <div className="flex items-center gap-3">
        {icon && (
          <span className="text-xl text-blue-600">
            {icon}
          </span>
        )}
        <Title level={2} className="!mb-0 !mt-0">{title}</Title>
        {serverTag && (
          <Tag color="blue" className="ml-0">
            {serverTag}
          </Tag>
        )}
      </div>
      {actions && (
        <Space>
          {actions}
        </Space>
      )}
    </div>
  )
}

export default PageHeader