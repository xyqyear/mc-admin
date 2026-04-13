import React, { useState, useMemo } from 'react';
import {
  Users,
  RotateCw,
  Clock,
  Calendar,
} from 'lucide-react';
import {
  type ColumnDef,
  type SortingState,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';

import PageHeader from '@/components/layout/PageHeader';
import { DataTable } from '@/components/common/DataTable';
import { SortableHeader } from '@/components/common/SortableHeader';
import { EmptyState } from '@/components/common/EmptyState';
import { PlayerOnlineBadge } from '@/components/common/PlayerOnlineBadge';
import PlayerFilters from '@/components/players/PlayerFilters';
import PlayerDetailDialog from '@/components/players/PlayerDetailDialog';
import { MCAvatar } from '@/components/players/MCAvatar';
import { useAllPlayers } from '@/hooks/queries/base/usePlayerQueries';
import { useServerQueries } from '@/hooks/queries/base/useServerQueries';
import type { PlayerSummary } from '@/hooks/api/playerApi';
import { formatUUID } from '@/utils/formatUtils';

const formatDuration = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return `${days}天 ${remainingHours}小时`;
  }
  if (hours > 0) {
    return `${hours}小时 ${minutes}分钟`;
  }
  return `${minutes}分钟`;
};

// --- Column definitions ---

const columns: ColumnDef<PlayerSummary, any>[] = [
  {
    id: 'player',
    accessorKey: 'current_name',
    header: '玩家',
    cell: ({ row }) => (
      <div className="flex items-center space-x-3">
        <MCAvatar
          avatarBase64={row.original.avatar_base64}
          size={40}
          playerName={row.original.current_name}
        />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-base truncate" title={row.original.current_name}>
            {row.original.current_name}
          </div>
          <div className="text-xs text-muted-foreground truncate" title={formatUUID(row.original.uuid)}>
            UUID: {formatUUID(row.original.uuid)}
          </div>
        </div>
      </div>
    ),
    enableSorting: false,
    size: 250,
  },
  {
    accessorKey: 'is_online',
    header: '状态',
    cell: ({ row }) => (
      <PlayerOnlineBadge online={row.getValue<boolean>('is_online')} />
    ),
    size: 100,
  },
  {
    accessorKey: 'total_playtime_seconds',
    header: ({ column }) => <SortableHeader column={column} title="总游戏时长" />,
    cell: ({ row }) => (
      <span className="flex items-center gap-1.5" title={`${row.getValue<number>('total_playtime_seconds')}秒`}>
        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
        {formatDuration(row.getValue<number>('total_playtime_seconds'))}
      </span>
    ),
    size: 150,
  },
  {
    accessorKey: 'first_seen',
    header: ({ column }) => <SortableHeader column={column} title="首次加入" />,
    cell: ({ row }) => (
      <span className="flex items-center gap-1.5">
        <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
        {new Date(row.getValue<string>('first_seen')).toLocaleString('zh-CN')}
      </span>
    ),
    sortingFn: (a, b) =>
      new Date(a.getValue<string>('first_seen')).getTime() -
      new Date(b.getValue<string>('first_seen')).getTime(),
    size: 180,
  },
  {
    accessorKey: 'last_seen',
    header: ({ column }) => <SortableHeader column={column} title="最后在线" />,
    cell: ({ row }) => {
      const date = row.getValue<string | null>('last_seen');
      return (
        <span className="flex items-center gap-1.5">
          <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
          {date ? new Date(date).toLocaleString('zh-CN') : '从未上线'}
        </span>
      );
    },
    sortingFn: (a, b) => {
      const aTime = a.getValue<string | null>('last_seen')
        ? new Date(a.getValue<string>('last_seen')).getTime()
        : 0;
      const bTime = b.getValue<string | null>('last_seen')
        ? new Date(b.getValue<string>('last_seen')).getTime()
        : 0;
      return aTime - bTime;
    },
    size: 180,
  },
  {
    id: 'actions',
    header: '操作',
    cell: () => null, // filled dynamically via meta
    size: 100,
  },
];

const PlayerManagement: React.FC = () => {
  const [selectedPlayerUUID, setSelectedPlayerUUID] = useState<string | null>(null);
  const [filters, setFilters] = useState<{
    online_only?: boolean;
    server_id?: string;
    search?: string;
  }>({});

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'last_seen', desc: true },
  ]);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 });

  const { useServers } = useServerQueries();
  const { data: servers = [] } = useServers();

  const {
    data: allPlayers = [],
    isLoading,
    error,
    refetch,
  } = useAllPlayers({
    online_only: filters.online_only,
    server_id: filters.server_id,
  });

  // Client-side search filter
  const filteredPlayers = useMemo(() => {
    if (!filters.search) return allPlayers;
    const searchLower = filters.search.toLowerCase();
    return allPlayers.filter(
      player =>
        player.current_name.toLowerCase().includes(searchLower) ||
        player.uuid.toLowerCase().includes(searchLower)
    );
  }, [allPlayers, filters.search]);

  const serverOptions = useMemo(
    () =>
      servers.map(server => ({
        label: server.name,
        value: server.id,
      })),
    [servers]
  );

  // Build columns with the action cell closure
  const tableColumns = useMemo<ColumnDef<PlayerSummary, any>[]>(() => {
    return columns.map(col => {
      if (col.id === 'actions') {
        return {
          ...col,
          cell: ({ row }) => (
            <Button
              variant="link"
              size="sm"
              onClick={() => setSelectedPlayerUUID(row.original.uuid)}
            >
              查看详情
            </Button>
          ),
        } as ColumnDef<PlayerSummary, any>;
      }
      return col;
    });
  }, []);

  const table = useReactTable({
    data: filteredPlayers,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    state: { sorting, pagination },
    autoResetPageIndex: false,
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="玩家管理"
        icon={<Users className="h-5 w-5" />}
        actions={
          <Button
            variant="outline"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            {isLoading
              ? <Spinner className="mr-2 size-4" />
              : <RotateCw className="mr-2 h-4 w-4" />
            }
            刷新
          </Button>
        }
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>加载玩家数据失败</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            <span>{error.message || '发生未知错误'}</span>
            <Button size="sm" variant="destructive" onClick={() => refetch()}>
              重试
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              <span>玩家列表</span>
              <span className="text-sm font-normal text-muted-foreground">
                ({filteredPlayers.length} 个玩家)
              </span>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PlayerFilters
            serverOptions={serverOptions}
            filters={filters}
            onChange={(f) => { setFilters(f); setPagination(prev => ({ ...prev, pageIndex: 0 })); }}
            onReset={() => { setFilters({}); setPagination(prev => ({ ...prev, pageIndex: 0 })); }}
            loading={isLoading}
          />

          <DataTable
            table={table}
            isLoading={isLoading}
            rowLabel="个玩家"
            emptyMessage={
              <EmptyState
                title="暂无玩家数据"
                description="玩家数据会在玩家首次加入服务器时自动记录"
              />
            }
          />
        </CardContent>
      </Card>

      <PlayerDetailDialog
        uuid={selectedPlayerUUID}
        open={!!selectedPlayerUUID}
        onClose={() => setSelectedPlayerUUID(null)}
      />
    </div>
  );
};

export default PlayerManagement;
