import React from 'react';
import { Copy, Link } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useDNSEnabled, useRouterRoutes } from '@/hooks/queries/base/useDnsQueries';
import LoadingSpinner from '@/components/layout/LoadingSpinner';

interface ServerAddressCardProps {
  serverId: string;
  className?: string;
}

const CardTitleRow = () => (
  <div className="flex items-center gap-2">
    <Link className="h-4 w-4" />
    <span>服务器地址</span>
  </div>
);

export const ServerAddressCard: React.FC<ServerAddressCardProps> = ({ serverId, className }) => {
  const { data: dnsEnabled, isLoading: enabledLoading } = useDNSEnabled();
  const isDNSEnabled = dnsEnabled?.enabled ?? false;
  const { data: routerRoutes, isLoading: routesLoading, error } = useRouterRoutes(isDNSEnabled);

  const addresses = React.useMemo(() => {
    if (!routerRoutes) return [];
    return Object.keys(routerRoutes)
      .filter(serverAddress => serverAddress.startsWith(serverId));
  }, [routerRoutes, serverId]);

  const handleCopyAddress = async (address: string) => {
    await navigator.clipboard.writeText(address);
    toast.success(`地址已复制: ${address}`);
  };

  const isLoading = enabledLoading || routesLoading;

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base"><CardTitleRow /></CardTitle>
        </CardHeader>
        <CardContent>
          <LoadingSpinner height="4rem" />
        </CardContent>
      </Card>
    );
  }

  if (!isDNSEnabled) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base"><CardTitleRow /></CardTitle>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertTitle>DNS管理未启用</AlertTitle>
            <AlertDescription>请前往设置页面启用DNS管理功能以查看服务器地址</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base"><CardTitleRow /></CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTitle>加载路由信息失败</AlertTitle>
            <AlertDescription>{String(error)}</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (addresses.length === 0) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base"><CardTitleRow /></CardTitle>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertTitle>未找到服务器地址</AlertTitle>
            <AlertDescription>没有找到与该服务器匹配的路由地址</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base"><CardTitleRow /></CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {addresses.map((address) => (
            <div key={address} className="flex items-center space-x-3">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => handleCopyAddress(address)}
                title={`Copy ${address}`}
              >
                <Copy className="h-4 w-4" />
              </Button>
              <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">
                {address}
              </code>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default ServerAddressCard;
