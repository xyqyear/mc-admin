import React, { useState } from 'react';
import {
  User,
  Clock,
  MessageSquare,
  Trophy,
  Calendar,
} from 'lucide-react';
import {
  type ColumnDef,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

import { DataTable } from '@/components/common/DataTable';
import { StatusBadge } from '@/components/common/StatusBadge';
import { PlayerOnlineBadge } from '@/components/common/PlayerOnlineBadge';
import { RefreshButton } from '@/components/common/RefreshButton';
import {
  usePlayerByUUID,
  usePlayerSessions,
  usePlayerSessionStats,
  usePlayerChat,
  usePlayerAchievements,
} from '@/hooks/queries/base/usePlayerQueries';
import type {
  SessionInfo,
  ChatMessageInfo,
  AchievementInfo,
} from '@/hooks/api/playerApi';
import { usePlayerMutations } from '@/hooks/mutations/usePlayerMutations';
import LoadingSpinner from '@/components/layout/LoadingSpinner';
import { MCAvatar } from '@/components/players/MCAvatar';
import { ServerNameTag } from '@/components/common/ServerNameTag';
import { formatUUID } from '@/utils/formatUtils';

interface PlayerDetailDialogProps {
  uuid: string | null;
  open: boolean;
  onClose: () => void;
}

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

// --- Data table helper ---

function PlayerTabTable<TData>({
  columns,
  data,
  isLoading,
  emptyMessage,
}: {
  columns: ColumnDef<TData, any>[];
  data: TData[];
  isLoading?: boolean;
  emptyMessage: string;
}) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 10 } },
    autoResetPageIndex: false,
  });

  return (
    <DataTable
      table={table}
      isLoading={isLoading}
      emptyMessage={emptyMessage}
      pageSizeOptions={[10, 20, 50]}
    />
  );
}

// --- Column definitions ---

const sessionColumns: ColumnDef<SessionInfo, any>[] = [
  {
    accessorKey: 'server_id',
    header: '服务器',
    cell: ({ row }) => <ServerNameTag serverId={row.getValue('server_id')} />,
    size: 150,
  },
  {
    accessorKey: 'joined_at',
    header: '加入时间',
    cell: ({ row }) => new Date(row.getValue<string>('joined_at')).toLocaleString('zh-CN'),
    size: 180,
  },
  {
    accessorKey: 'left_at',
    header: '离开时间',
    cell: ({ row }) => {
      const leftAt = row.getValue<string | null>('left_at');
      return leftAt
        ? new Date(leftAt).toLocaleString('zh-CN')
        : <StatusBadge tone="success">在线中</StatusBadge>;
    },
    size: 180,
  },
  {
    accessorKey: 'duration_seconds',
    header: '游戏时长',
    cell: ({ row }) => {
      const seconds = row.getValue<number | null>('duration_seconds');
      return seconds !== null ? formatDuration(seconds) : '-';
    },
    size: 120,
  },
];

const chatColumns: ColumnDef<ChatMessageInfo, any>[] = [
  {
    accessorKey: 'sent_at',
    header: '时间',
    cell: ({ row }) => new Date(row.getValue<string>('sent_at')).toLocaleString('zh-CN'),
    size: 180,
  },
  {
    accessorKey: 'server_id',
    header: '服务器',
    cell: ({ row }) => <ServerNameTag serverId={row.getValue('server_id')} maxLength={15} />,
    size: 120,
  },
  {
    accessorKey: 'message_text',
    header: '消息内容',
    cell: ({ row }) => (
      <span className="truncate block max-w-75" title={row.getValue<string>('message_text')}>
        {row.getValue<string>('message_text')}
      </span>
    ),
  },
];

const achievementColumns: ColumnDef<AchievementInfo, any>[] = [
  {
    accessorKey: 'achievement_name',
    header: '成就名称',
    cell: ({ row }) => (
      <span className="truncate block max-w-50" title={row.getValue<string>('achievement_name')}>
        {row.getValue<string>('achievement_name')}
      </span>
    ),
  },
  {
    accessorKey: 'server_id',
    header: '服务器',
    cell: ({ row }) => <ServerNameTag serverId={row.getValue('server_id')} maxLength={15} />,
    size: 120,
  },
  {
    accessorKey: 'earned_at',
    header: '获得时间',
    cell: ({ row }) => new Date(row.getValue<string>('earned_at')).toLocaleString('zh-CN'),
    size: 180,
  },
];

// --- Skin preview dialog ---

const SkinPreviewDialog: React.FC<{
  skinBase64: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}> = ({ skinBase64, open, onOpenChange }) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={() => onOpenChange(false)}
    >
      <img
        src={`data:image/png;base64,${skinBase64}`}
        alt="Player Skin"
        className="w-64 h-auto"
        style={{ imageRendering: 'pixelated' }}
        onClick={e => e.stopPropagation()}
      />
    </div>
  );
};

// --- Main component ---

export const PlayerDetailDialog: React.FC<PlayerDetailDialogProps> = ({
  uuid,
  open,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [skinPreviewOpen, setSkinPreviewOpen] = useState(false);
  const { useRefreshPlayerSkin } = usePlayerMutations();
  const refreshPlayerSkinMutation = useRefreshPlayerSkin();

  const { data: player, isLoading: playerLoading } = usePlayerByUUID(uuid);

  const { data: sessions = [], isLoading: sessionsLoading } = usePlayerSessions(
    player?.player_db_id || null,
    { limit: 50 }
  );

  const { data: sessionStats } = usePlayerSessionStats(
    player?.player_db_id || null,
    'all'
  );

  const { data: chatMessages = [], isLoading: chatLoading } = usePlayerChat(
    player?.player_db_id || null,
    { limit: 100 }
  );

  const { data: achievements = [], isLoading: achievementsLoading } = usePlayerAchievements(
    player?.player_db_id || null
  );

  const handleRefreshSkin = async () => {
    if (!player) return;
    try {
      await refreshPlayerSkinMutation.mutateAsync(player.player_db_id);
      toast.success('皮肤刷新请求已发送，请稍后查看');
    } catch (error: any) {
      toast.error(`刷新失败: ${error.message || '未知错误'}`);
    }
  };

  if (!open) return null;

  return (
    <>
      <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
        <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <User className="h-4 w-4" />
              <span>玩家详情</span>
              {player && <PlayerOnlineBadge online={player.is_online} />}
            </DialogTitle>
            <DialogDescription className="sr-only">
              Player detail information
            </DialogDescription>
          </DialogHeader>

          {playerLoading ? (
            <LoadingSpinner height="16rem" />
          ) : !player ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <User className="h-12 w-12 mb-4" />
              <p>未找到玩家信息</p>
            </div>
          ) : (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="overview">
                  <User className="mr-1.5 h-3.5 w-3.5" />
                  概览
                </TabsTrigger>
                <TabsTrigger value="sessions">
                  <Calendar className="mr-1.5 h-3.5 w-3.5" />
                  游戏会话 ({sessions.length})
                </TabsTrigger>
                <TabsTrigger value="chat">
                  <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
                  聊天记录 ({chatMessages.length})
                </TabsTrigger>
                <TabsTrigger value="achievements">
                  <Trophy className="mr-1.5 h-3.5 w-3.5" />
                  成就 ({achievements.length})
                </TabsTrigger>
              </TabsList>

              {/* Overview tab */}
              <TabsContent value="overview" className="space-y-4 mt-4">
                {/* Basic info */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">基本信息</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-start gap-6">
                      {/* Avatar and skin */}
                      <div className="flex flex-col items-center gap-2">
                        <MCAvatar
                          avatarBase64={player.avatar_base64}
                          size={80}
                          playerName={player.current_name}
                        />
                        {player.skin_base64 && (
                          <img
                            src={`data:image/png;base64,${player.skin_base64}`}
                            alt="Player Skin"
                            className="w-16 cursor-pointer hover:opacity-80 transition-opacity"
                            style={{ imageRendering: 'pixelated' }}
                            onClick={() => setSkinPreviewOpen(true)}
                            title="查看皮肤"
                          />
                        )}
                        <RefreshButton
                          size="sm"
                          isRefreshing={refreshPlayerSkinMutation.isPending}
                          onClick={handleRefreshSkin}
                          label="刷新皮肤"
                        />
                      </div>

                      {/* Details */}
                      <dl className="flex-1 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                        <dt className="text-muted-foreground">玩家名称</dt>
                        <dd className="font-semibold text-lg">{player.current_name}</dd>

                        <dt className="text-muted-foreground">UUID</dt>
                        <dd>
                          <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">
                            {formatUUID(player.uuid)}
                          </code>
                        </dd>

                        <dt className="text-muted-foreground">当前在线</dt>
                        <dd>
                          {player.current_servers.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {player.current_servers.map(serverId => (
                                <ServerNameTag key={serverId} serverId={serverId} />
                              ))}
                            </div>
                          ) : (
                            <span className="text-muted-foreground">当前离线</span>
                          )}
                        </dd>

                        <dt className="text-muted-foreground">首次加入</dt>
                        <dd>{new Date(player.first_seen).toLocaleString('zh-CN')}</dd>

                        <dt className="text-muted-foreground">最后在线</dt>
                        <dd>
                          {player.last_seen
                            ? new Date(player.last_seen).toLocaleString('zh-CN')
                            : '从未上线'}
                        </dd>
                      </dl>
                    </div>
                  </CardContent>
                </Card>

                {/* Stats */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">统计数据</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">总游戏时长</p>
                        <p className="text-xl font-semibold flex items-center gap-1.5">
                          <Clock className="h-4 w-4 text-muted-foreground" />
                          {formatDuration(player.total_playtime_seconds)}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">总会话数</p>
                        <p className="text-xl font-semibold flex items-center gap-1.5">
                          <Calendar className="h-4 w-4 text-muted-foreground" />
                          {player.total_sessions}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">聊天消息数</p>
                        <p className="text-xl font-semibold flex items-center gap-1.5">
                          <MessageSquare className="h-4 w-4 text-muted-foreground" />
                          {player.total_messages}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">获得成就数</p>
                        <p className="text-xl font-semibold flex items-center gap-1.5">
                          <Trophy className="h-4 w-4 text-muted-foreground" />
                          {player.total_achievements}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Session stats */}
                {sessionStats && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base">会话统计</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-sm text-muted-foreground">平均会话时长</p>
                          <p className="text-xl font-semibold">
                            {formatDuration(sessionStats.average_session_seconds)}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">最长会话时长</p>
                          <p className="text-xl font-semibold">
                            {formatDuration(sessionStats.longest_session_seconds)}
                          </p>
                        </div>
                      </div>

                      {Object.keys(sessionStats.playtime_by_server).length > 0 && (
                        <div className="mt-4">
                          <p className="font-medium text-sm mb-2">各服务器游戏时长</p>
                          <div className="space-y-2">
                            {Object.entries(sessionStats.playtime_by_server).map(([serverId, seconds]) => (
                              <div key={serverId} className="flex justify-between items-center">
                                <ServerNameTag serverId={serverId} />
                                <span className="text-sm">{formatDuration(seconds)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </TabsContent>

              {/* Sessions tab */}
              <TabsContent value="sessions" className="mt-4">
                <PlayerTabTable
                  columns={sessionColumns}
                  data={sessions}
                  isLoading={sessionsLoading}
                  emptyMessage="暂无会话记录"
                />
              </TabsContent>

              {/* Chat tab */}
              <TabsContent value="chat" className="mt-4">
                <PlayerTabTable
                  columns={chatColumns}
                  data={chatMessages}
                  isLoading={chatLoading}
                  emptyMessage="暂无聊天记录"
                />
              </TabsContent>

              {/* Achievements tab */}
              <TabsContent value="achievements" className="mt-4">
                <PlayerTabTable
                  columns={achievementColumns}
                  data={achievements}
                  isLoading={achievementsLoading}
                  emptyMessage="暂无成就记录"
                />
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      {player?.skin_base64 && (
        <SkinPreviewDialog
          skinBase64={player.skin_base64}
          open={skinPreviewOpen}
          onOpenChange={setSkinPreviewOpen}
        />
      )}
    </>
  );
};

export default PlayerDetailDialog;
