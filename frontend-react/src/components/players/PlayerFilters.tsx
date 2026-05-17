import React from 'react';
import { Search, XCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface PlayerFiltersProps {
  serverOptions: { label: string; value: string }[];
  filters: {
    online_only?: boolean;
    server_id?: string;
    search?: string;
  };
  onChange: (filters: {
    online_only?: boolean;
    server_id?: string;
    search?: string;
  }) => void;
  onReset: () => void;
  loading?: boolean;
}

const ALL_VALUE = '__all__';

export const PlayerFilters: React.FC<PlayerFiltersProps> = ({
  serverOptions,
  filters,
  onChange,
  onReset,
  loading
}) => {
  const handleOnlineFilterChange = (value: string | null) => {
    onChange({
      ...filters,
      online_only: value === 'online' ? true : value === 'offline' ? false : undefined
    });
  };

  const handleServerChange = (value: string | null) => {
    onChange({
      ...filters,
      server_id: (!value || value === ALL_VALUE) ? undefined : value
    });
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({
      ...filters,
      search: e.target.value || undefined
    });
  };

  const hasActiveFilters = filters.online_only !== undefined ||
    filters.server_id !== undefined ||
    filters.search !== undefined;

  const onlineFilterValue = filters.online_only === true
    ? 'online'
    : filters.online_only === false
      ? 'offline'
      : ALL_VALUE;

  const onlineLabels: Record<string, string> = {
    [ALL_VALUE]: '全部',
    online: '仅在线',
    offline: '仅离线',
  };

  return (
    <div className="mb-4 p-4 bg-muted/50 rounded-lg">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-muted-foreground">在线状态</span>
          <Select value={onlineFilterValue} onValueChange={handleOnlineFilterChange}>
            <SelectTrigger className="w-37.5">
              <SelectValue placeholder="全部">
                {(value: string) => onlineLabels[value] ?? '全部'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>全部</SelectItem>
              <SelectItem value="online">仅在线</SelectItem>
              <SelectItem value="offline">仅离线</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-sm text-muted-foreground">服务器</span>
          <Select value={filters.server_id ?? ALL_VALUE} onValueChange={handleServerChange}>
            <SelectTrigger className="w-50">
              <SelectValue placeholder="全部服务器">
                {(value: string) => {
                  if (!value || value === ALL_VALUE) return '全部服务器';
                  return serverOptions.find(s => s.value === value)?.label ?? '全部服务器';
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>全部服务器</SelectItem>
              {serverOptions.map(opt => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1 flex-1 min-w-50">
          <span className="text-sm text-muted-foreground">搜索玩家</span>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="输入玩家名称搜索"
              value={filters.search ?? ''}
              onChange={handleSearchChange}
            />
          </div>
        </div>

        <Button
          variant="outline"
          onClick={onReset}
          disabled={!hasActiveFilters || loading}
        >
          <XCircle className="mr-2 h-4 w-4" />
          重置
        </Button>
      </div>
    </div>
  );
};

export default PlayerFilters;
