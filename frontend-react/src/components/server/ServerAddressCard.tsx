import React from 'react';
import { Card, Typography, Button, Space, message, Alert } from 'antd';
import { CopyOutlined, LinkOutlined } from '@ant-design/icons';
import { useRouterRoutes } from '@/hooks/queries/base/useDnsQueries';
import LoadingSpinner from '@/components/layout/LoadingSpinner';

const { Title, Text } = Typography;

interface ServerAddressCardProps {
  serverId: string;
  className?: string;
}

export const ServerAddressCard: React.FC<ServerAddressCardProps> = ({ serverId, className }) => {
  const { data: routerRoutes, isLoading, error } = useRouterRoutes();

  // 筛选出以 serverId 开头的路由地址
  const addresses = React.useMemo(() => {
    if (!routerRoutes) return [];

    return Object.keys(routerRoutes)
      .filter(serverAddress => serverAddress.startsWith(serverId));
  }, [routerRoutes, serverId]);

  const handleCopyAddress = async (address: string) => {
    await navigator.clipboard.writeText(address);
    message.success(`地址已复制: ${address}`);
  };

  if (isLoading) {
    return (
      <Card
        className={className}
        title={
          <Space align="center">
            <LinkOutlined />
            <Title level={5} style={{ margin: 0 }}>
              服务器地址
            </Title>
          </Space>
        }
      >
        <LoadingSpinner height="4rem" tip="加载路由信息中..." />
      </Card>
    );
  }

  if (error) {
    return (
      <Card
        className={className}
        title={
          <Space align="center">
            <LinkOutlined />
            <Title level={5} style={{ margin: 0 }}>
              服务器地址
            </Title>
          </Space>
        }
      >
        <Alert
          message="加载路由信息失败"
          description={String(error)}
          type="error"
          showIcon
        />
      </Card>
    );
  }

  if (addresses.length === 0) {
    return (
      <Card
        className={className}
        title={
          <Space align="center">
            <LinkOutlined />
            <Title level={5} style={{ margin: 0 }}>
              服务器地址
            </Title>
          </Space>
        }
      >
        <Alert
          message="未找到服务器地址"
          description="没有找到与该服务器匹配的路由地址"
          type="info"
          showIcon
        />
      </Card>
    );
  }

  return (
    <Card
      className={className}
      title={
        <Space align="center">
          <LinkOutlined />
          <Title level={5} style={{ margin: 0 }}>
            服务器地址
          </Title>
        </Space>
      }
    >
      <div className="space-y-3">
        {addresses.map((address) => {
          return (
            <div key={address} className="flex items-center space-x-3">
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopyAddress(address)}
                className="flex-shrink-0"
                title={`Copy ${address}`}
              />
              <Text
                code
                className="text-sm font-mono"
                style={{ fontSize: '13px' }}
              >
                {address}
              </Text>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

export default ServerAddressCard;