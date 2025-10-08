import React from 'react';
import { Space, Select, Button, Input } from 'antd';
import { ClearOutlined } from '@ant-design/icons';

const { Search } = Input;

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

export const PlayerFilters: React.FC<PlayerFiltersProps> = ({
  serverOptions,
  filters,
  onChange,
  onReset,
  loading
}) => {
  const handleOnlineFilterChange = (value: string | undefined) => {
    onChange({
      ...filters,
      online_only: value === 'online' ? true : value === 'offline' ? false : undefined
    });
  };

  const handleServerChange = (value: string | undefined) => {
    onChange({
      ...filters,
      server_id: value
    });
  };

  const handleSearchChange = (value: string) => {
    onChange({
      ...filters,
      search: value || undefined
    });
  };

  const hasActiveFilters = filters.online_only !== undefined ||
    filters.server_id !== undefined ||
    filters.search !== undefined;

  return (
    <div className="mb-4 p-4 bg-gray-50 rounded-lg">
      <Space wrap size="middle" className="w-full">
        <div className="flex flex-col">
          <span className="text-sm text-gray-600 mb-1">在线状态</span>
          <Select
            style={{ width: 150 }}
            placeholder="全部"
            allowClear
            value={
              filters.online_only === true
                ? 'online'
                : filters.online_only === false
                  ? 'offline'
                  : undefined
            }
            onChange={handleOnlineFilterChange}
            options={[
              { label: '仅在线', value: 'online' },
              { label: '仅离线', value: 'offline' }
            ]}
          />
        </div>

        <div className="flex flex-col">
          <span className="text-sm text-gray-600 mb-1">服务器</span>
          <Select
            style={{ width: 200 }}
            placeholder="全部服务器"
            allowClear
            value={filters.server_id}
            onChange={handleServerChange}
            options={serverOptions}
          />
        </div>

        <div className="flex flex-col flex-1" style={{ minWidth: '200px' }}>
          <span className="text-sm text-gray-600 mb-1">搜索玩家</span>
          <Search
            placeholder="输入玩家名称搜索"
            allowClear
            value={filters.search}
            onChange={(e) => handleSearchChange(e.target.value)}
            onSearch={handleSearchChange}
            style={{ width: '100%' }}
          />
        </div>

        <div className="flex flex-col justify-end">
          <Space>
            <Button
              icon={<ClearOutlined />}
              onClick={onReset}
              disabled={!hasActiveFilters || loading}
            >
              重置
            </Button>
          </Space>
        </div>
      </Space>
    </div>
  );
};

export default PlayerFilters;
