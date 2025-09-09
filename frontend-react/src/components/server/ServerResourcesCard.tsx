import React from 'react';
import { Card, Row, Col, Progress } from 'antd';
import { ServerInfo } from '@/types/ServerInfo';

interface ServerResourcesCardProps {
  cpuPercentage?: number;
  memoryUsageBytes?: number;
  serverInfo: ServerInfo;
  isRunning: boolean;
  hasCpuData: boolean;
  hasMemoryData: boolean;
  className?: string;
}

export const ServerResourcesCard: React.FC<ServerResourcesCardProps> = ({
  cpuPercentage,
  memoryUsageBytes,
  serverInfo,
  isRunning,
  hasCpuData,
  hasMemoryData,
  className
}) => {
  if (!isRunning || (!hasCpuData && !hasMemoryData) ||
    (cpuPercentage === undefined && memoryUsageBytes === undefined)) {
    return null;
  }

  return (
    <Card title="系统资源使用情况" className={className}>
      <Row gutter={[16, 16]}>
        {hasCpuData && cpuPercentage !== undefined && (
          <Col span={12}>
            <div>
              <div className="flex justify-between mb-1">
                <span>CPU 使用率</span>
                <span>{cpuPercentage.toFixed(1)}%</span>
              </div>
              <Progress
                percent={cpuPercentage}
                strokeColor={cpuPercentage > 80 ? '#ff4d4f' : cpuPercentage > 60 ? '#faad14' : '#52c41a'}
                showInfo={false}
              />
            </div>
          </Col>
        )}
        {hasMemoryData && memoryUsageBytes !== undefined && (
          <Col span={12}>
            <div>
              <div className="flex justify-between mb-1">
                <span>内存使用</span>
                <span>
                  {(memoryUsageBytes / (1024 ** 3)).toFixed(1)}GB /
                  {(serverInfo.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB
                </span>
              </div>
              <Progress
                percent={(memoryUsageBytes / serverInfo.maxMemoryBytes) * 100}
                strokeColor={(memoryUsageBytes / serverInfo.maxMemoryBytes) > 0.8 ? '#ff4d4f' :
                  (memoryUsageBytes / serverInfo.maxMemoryBytes) > 0.6 ? '#faad14' : '#52c41a'}
                showInfo={false}
              />
            </div>
          </Col>
        )}
      </Row>
    </Card>
  );
};

export default ServerResourcesCard;