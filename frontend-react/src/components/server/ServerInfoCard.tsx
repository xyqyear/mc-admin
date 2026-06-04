import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import type { ServerInfo } from '@/types/ServerInfo';

interface ServerInfoCardProps {
  serverInfo: ServerInfo;
  className?: string;
}

export const ServerInfoCard: React.FC<ServerInfoCardProps> = ({ serverInfo, className }) => {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">服务器详情</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">服务器ID</dt>
          <dd>{serverInfo.id}</dd>
          <dt className="text-muted-foreground">服务器类型</dt>
          <dd>{serverInfo.serverType}</dd>
          <dt className="text-muted-foreground">游戏版本</dt>
          <dd>{serverInfo.gameVersion}</dd>
          <dt className="text-muted-foreground">Java版本</dt>
          <dd>{serverInfo.javaVersion}</dd>
          <dt className="text-muted-foreground">游戏端口</dt>
          <dd>{serverInfo.gamePort}</dd>
          <dt className="text-muted-foreground">RCON端口</dt>
          <dd>{serverInfo.rconPort}</dd>
          <dt className="text-muted-foreground">最大内存</dt>
          <dd>{(serverInfo.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB</dd>
          <dt className="text-muted-foreground">服务器路径</dt>
          <dd className="break-all">{serverInfo.path}</dd>
        </dl>
      </CardContent>
    </Card>
  );
};

export default ServerInfoCard;
