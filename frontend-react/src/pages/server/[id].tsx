import React from 'react'
import { Typography } from 'antd'
import { useParams } from 'react-router-dom'

const { Title } = Typography

const ServerDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()

  return (
    <div>
      <Title level={2}>服务器详情</Title>
      <div className="flex justify-center items-center min-h-64">
        <span className="text-xl">服务器 ID: {id}</span>
      </div>
    </div>
  )
}

export default ServerDetail
