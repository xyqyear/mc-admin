import React from 'react'
import { Card, CardContent } from '@/components/ui/card'

interface ServerCountCardProps {
  totalServers: number
  runningServers: number
}

const ServerCountCard: React.FC<ServerCountCardProps> = ({ totalServers, runningServers }) => {
  return (
    <Card className="h-full w-full">
      <CardContent className="h-full flex flex-col items-center justify-center text-center">
        <div className="text-3xl sm:text-4xl font-bold text-foreground mb-3">
          {runningServers}/{totalServers}
        </div>
        <div className="text-sm sm:text-base font-semibold text-muted-foreground mb-2">
          服务器状态
        </div>
        <div className="text-xs text-muted-foreground">
          运行中/总数
        </div>
      </CardContent>
    </Card>
  )
}

export default ServerCountCard
