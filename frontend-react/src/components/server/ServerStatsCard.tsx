import React from 'react';
import { Card, Row, Col, Statistic } from 'antd';
import { UserOutlined, GlobalOutlined, HddOutlined, WifiOutlined } from '@ant-design/icons';
import { ServerInfo } from '@/types/ServerInfo';

interface ServerStatsCardProps {
  serverInfo: ServerInfo;
  playersCount: number;
  isRunning: boolean;
  className?: string;
}

export const ServerStatsCard: React.FC<ServerStatsCardProps> = ({
  serverInfo,
  playersCount,
  isRunning,
  className
}) => {
  return (
    <Card className={className}>
      <Row gutter={16}>
        <Col span={6}>
          <Statistic
            title="在线玩家"
            value={playersCount}
            suffix={`/ ${20}`} // 默认最大玩家数，后续可从配置获取
            prefix={<UserOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="游戏端口"
            value={serverInfo.gamePort}
            formatter={(value) => `${value}`}
            prefix={<GlobalOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="RCON端口"
            value={serverInfo.rconPort}
            formatter={(value) => `${value}`}
            prefix={<HddOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="运行时间"
            value={isRunning ? '运行中' : '未运行'}
            prefix={<WifiOutlined />}
          />
        </Col>
      </Row>
    </Card>
  );
};

export default ServerStatsCard;