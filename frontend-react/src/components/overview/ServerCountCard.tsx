import React from 'react'
import { Card } from 'antd'

interface ServerCountCardProps {
  totalServers: number
  runningServers: number
}

const ServerCountCard: React.FC<ServerCountCardProps> = ({ totalServers, runningServers }) => {
  return (
    <Card
      className="h-full w-full"
      styles={{
        body: {
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center'
        }
      }}
    >
      <div>
        <div className="text-3xl sm:text-4xl font-bold text-gray-800 mb-3">
          {runningServers}/{totalServers}
        </div>
        <div className="text-sm sm:text-base font-semibold text-gray-600 mb-2">
          服务器状态
        </div>
        <div className="text-xs text-gray-500">
          运行中/总数
        </div>
      </div>
    </Card>
  )
}

export default ServerCountCard