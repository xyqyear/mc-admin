import React from 'react';
import { Card, Descriptions } from 'antd';
import { ServerInfo } from '@/types/ServerInfo';

interface ServerInfoCardProps {
  serverInfo: ServerInfo;
  className?: string;
}

export const ServerInfoCard: React.FC<ServerInfoCardProps> = ({ serverInfo, className }) => {
  return (
    <Card title="服务器详情" className={className} size='small'>
      <Descriptions column={2}>
        <Descriptions.Item label="服务器ID">{serverInfo.id}</Descriptions.Item>
        <Descriptions.Item label="服务器类型">{serverInfo.serverType}</Descriptions.Item>
        <Descriptions.Item label="游戏版本">{serverInfo.gameVersion}</Descriptions.Item>
        <Descriptions.Item label="Java版本">{serverInfo.javaVersion}</Descriptions.Item>
        <Descriptions.Item label="游戏端口">{serverInfo.gamePort}</Descriptions.Item>
        <Descriptions.Item label="RCON端口">{serverInfo.rconPort}</Descriptions.Item>
        <Descriptions.Item label="最大内存">
          {(serverInfo.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB
        </Descriptions.Item>
        <Descriptions.Item label="服务器路径">{serverInfo.path}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
};

export default ServerInfoCard;