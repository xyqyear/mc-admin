import { Eraser, RefreshCw } from 'lucide-react'
import React from 'react'
import { useParams } from 'react-router'
import { useChunkPruneController } from '@/features/world/prune/useChunkPruneController'

import PageHeader from '@/shared/layout/PageHeader'
import ServerOperationButtons from '@/features/servers/ui/ServerOperationButtons'
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Card, CardContent } from '@/shared/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'
import { Skeleton } from '@/shared/ui/skeleton'
import { Spinner } from '@/shared/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { ClusterPopover } from '@/features/world/layers/claims/ClusterPopover'
import { TeamClusterList } from '@/features/world/layers/claims/TeamClusterList'
import { PlayerLocationList } from '@/features/world/layers/players/PlayerLocationList'
import type { ChunkKey } from '@/features/world/map/contracts'
import MapHelpButton from '@/features/world/map/MapHelpButton'
import MapInitDialog from '@/features/world/map/MapInitDialog'
import ServerMap from '@/features/world/map/ServerMap'
import ChunkPrunePanel from '@/features/world/prune/components/ChunkPrunePanel'

const ServerChunkPrune: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const serverId = id ?? ''
  const {
    layoutQ,
    statusQ,
    serverInfoQ,
    serverStopped,
    mapStatusQ,
    mapInitialized,
    initOpen,
    initForce,
    setInitOpen,
    setInitForce,
    handleInitComplete,
    handleRefreshMap,
    dimensionRelpath,
    initialView,
    regionRelpath,
    rootList,
    dimensionOptions,
    dimensionLabelByRelpath,
    handleDimensionChange,
    handleViewChange,
    regionsMap,
    regionsLoading,
    regionsError,
    claimsQ,
    claimsAvailable,
    claimsOverlayVisible,
    setClaimsOverlayVisible,
    claimsPopover,
    closeClaimsPopover,
    highlightClusters,
    handleRefreshClaims,
    handleClusterClick,
    popoverContext,
    playerLocationsQ,
    playersOverlayVisible,
    setPlayersOverlayVisible,
    onlinePlayersOnly,
    setOnlinePlayersOnly,
    onlinePlayersQ,
    onlinePlayerUuids,
    onlineStatusAvailable,
    playerProfiles,
    handleRefreshPlayers,
    handlePlayerClick,
    mapOverlays,
    urlMode,
    thresholdValue,
    setThresholdValue,
    thresholdUnit,
    setThresholdUnit,
    thresholdSeconds,
    previewStarting,
    cancelTask,
    previewTask,
    applyTask,
    previewStatus,
    applyStatus,
    previewResult,
    applyResult,
    previewError,
    applyError,
    applyActive,
    canPreview,
    canApply,
    startPreview,
    cancelPreview,
    startApply,
    cancelApply,
    handleModeChange,
    confirmDialog
  } = useChunkPruneController(serverId)

  if (!serverId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>错误</AlertTitle>
        <AlertDescription>缺少服务器ID</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <PageHeader
        title="区块清理"
        icon={<Eraser className="h-5 w-5" />}
        serverTag={serverId}
        actions={
          <>
            {layoutQ.isLoading ? (
              <>
                <Skeleton className="h-9 w-30" />
                <Skeleton className="h-9 w-65" />
              </>
            ) : dimensionOptions.length > 0 ? (
              <>
                {mapInitialized && (
                  <>
                    <Button
                      variant="outline"
                      onClick={handleRefreshMap}
                      title="重新读取世界元数据并刷新瓦片"
                    >
                      <RefreshCw className="mr-1 h-4 w-4" />
                      刷新地图
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={() => {
                        setInitForce(true)
                        setInitOpen(true)
                      }}
                      title="删除客户端 JAR 和调色板缓存后重新下载并生成"
                    >
                      重载渲染前置
                    </Button>
                  </>
                )}
                <Select
                  items={dimensionOptions}
                  value={dimensionRelpath ?? null}
                  onValueChange={(v) => {
                    if (typeof v === 'string') handleDimensionChange(v)
                  }}
                  itemToStringLabel={(v) =>
                    dimensionOptions.find((o) => o.value === v)?.label ??
                    String(v)
                  }
                >
                  <SelectTrigger className="w-65">
                    <SelectValue placeholder="选择维度" />
                  </SelectTrigger>
                  <SelectContent>
                    {dimensionOptions.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <MapHelpButton
                  title="区块清理说明"
                  description="预览会扫描服务器所有维度；当前选择的维度只影响地图上显示哪一部分结果。"
                >
                  <div className="space-y-3 text-sm">
                    <section>
                      <div className="mb-1 font-medium">清理机制</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>区块清理会删除 InhabitedTime 低于阈值的区块；这个值越低，通常说明区块被玩家长期使用或人工改动的可能性越低。</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">查看地图</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>按住鼠标左键/中键拖动：平移视角</li>
                        <li>滚轮：缩放</li>
                        <li>顶部维度选择：切换当前显示的维度</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">预览清理范围</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>设置清理阈值后点击“预览”</li>
                        <li>预览运行时只更新进度，不会实时绘制地图</li>
                        <li>预览完成后，地图会用红色覆盖层显示将被删除的区块或区域</li>
                        <li>切换维度只切换预览显示，不会重新扫描</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">清理模式</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>区块模式：逐个删除低于阈值的区块，同一区域内的高活跃区块会保留</li>
                        <li>区域模式：只有整个区域都符合条件时才删除该区域</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">FTB 领地保护</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>清理前会读取 FTB Claims / FTB Utilities 的领地数据</li>
                        <li>区块模式下，被领地声明的区块会跳过</li>
                        <li>区域模式下，只要区域内存在领地区块，整个区域都会保留</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">执行删除</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>只有当前阈值和模式仍匹配已完成预览时，才能执行删除</li>
                        <li>删除前需要先停止服务器</li>
                        <li>删除会作用于服务器所有维度，而不是当前显示的维度</li>
                        <li>删除会同时处理对应的 region、entities、poi 数据</li>
                        <li>删除完成后会刷新受影响的地图缓存</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">图层</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>领地图层用于确认受保护区域</li>
                        <li>玩家位置图层用于辅助判断哪些区域可能仍然重要</li>
                        <li>图层显示/隐藏只影响地图展示，不影响预览或删除范围</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">风险提示</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>InhabitedTime 是活跃度指标，不是“是否被人工修改”的绝对证明</li>
                        <li>执行删除前建议确认预览覆盖层，并确保最近有可用备份</li>
                      </ul>
                    </section>
                  </div>
                </MapHelpButton>
              </>
            ) : null}
            <ServerOperationButtons
              serverId={serverId}
              serverName={serverInfoQ.data?.name ?? serverId}
              status={statusQ.data}
              showReturnButton={false}
              maintenanceActive={applyActive}
            />
          </>
        }
      />

      {layoutQ.isError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取世界布局</AlertDescription>
        </Alert>
      )}

      {!layoutQ.isLoading && layoutQ.data && rootList.length === 0 && (
        <Alert>
          <AlertTitle>未发现世界</AlertTitle>
          <AlertDescription>
            该服务器的 data/ 目录下没有可识别的世界根（缺少 level.dat）。
          </AlertDescription>
        </Alert>
      )}

      {regionsError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取该维度的区域清单</AlertDescription>
        </Alert>
      )}

      {!mapStatusQ.isLoading && mapStatusQ.data && !mapInitialized && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-8">
            <div className="text-center text-muted-foreground">
              {!mapStatusQ.data.client_jar_present
                ? '尚未下载客户端 JAR。'
                : !mapStatusQ.data.palette_present
                  ? '尚未生成调色板。'
                  : '调色板已过期（版本或mods变更）。'}
            </div>
            <Button
              onClick={() => {
                setInitForce(false)
                setInitOpen(true)
              }}
            >
              初始化地图
            </Button>
          </CardContent>
        </Card>
      )}

      {(mapInitialized || layoutQ.isLoading) && (
        <div className="flex flex-col gap-4 md:grid md:min-h-0 md:flex-1 md:grid-cols-[1fr_270px] md:grid-rows-1">
          <Card className="overflow-hidden py-0">
            <CardContent className="h-[60vh] p-0 md:h-full md:min-h-[60vh]">
              {regionsMap && regionRelpath ? (
                <ServerMap
                  serverId={serverId}
                  regionPath={regionRelpath}
                  regions={regionsMap}
                  selectionMode="none"
                  overlays={mapOverlays}
                  initialView={initialView}
                  onViewChange={handleViewChange}
                />
              ) : layoutQ.isLoading || regionsLoading ? (
                <div className="flex h-[60vh] items-center justify-center md:h-full">
                  <Spinner />
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex min-w-0 flex-col md:min-h-0 md:overflow-y-auto md:*:shrink-0">
            <Card>
              <CardContent>
                <Tabs defaultValue="prune" className="gap-4">
                  <TabsList
                    className={
                      claimsAvailable
                        ? 'grid w-full grid-cols-3'
                        : 'grid w-full grid-cols-2'
                    }
                  >
                    <TabsTrigger value="prune">清理</TabsTrigger>
                    {claimsAvailable && (
                      <TabsTrigger value="claims">领地列表</TabsTrigger>
                    )}
                    <TabsTrigger value="players">玩家位置</TabsTrigger>
                  </TabsList>
                  <TabsContent value="prune">
                    <ChunkPrunePanel
                      thresholdValue={thresholdValue}
                      thresholdUnit={thresholdUnit}
                      thresholdSeconds={thresholdSeconds}
                      mode={urlMode}
                      previewStatus={previewStatus}
                      previewStarting={previewStarting}
                      previewProgress={previewTask?.progress ?? null}
                      previewMessage={previewTask?.message ?? null}
                      previewResult={previewResult}
                      previewError={previewError}
                      applyStatus={applyStatus}
                      applyProgress={applyTask?.progress ?? null}
                      applyMessage={applyTask?.message ?? null}
                      applyResult={applyResult}
                      applyError={applyError}
                      serverStopped={serverStopped}
                      canPreview={canPreview}
                      canApply={canApply}
                      cancellingPreview={cancelTask.isPending}
                      cancellingApply={cancelTask.isPending}
                      onThresholdValueChange={setThresholdValue}
                      onThresholdUnitChange={setThresholdUnit}
                      onModeChange={handleModeChange}
                      onPreview={startPreview}
                      onCancelPreview={cancelPreview}
                      onApply={startApply}
                      onCancelApply={cancelApply}
                    />
                  </TabsContent>
                  <TabsContent value="claims">
                    {claimsAvailable && (
                      <TeamClusterList
                        data={claimsQ.data}
                        isLoading={claimsQ.isLoading}
                        isError={claimsQ.isError}
                        currentDimRelpath={regionRelpath}
                        dimensionLabelByRelpath={dimensionLabelByRelpath}
                        mode={urlMode === 'regions' ? 'region' : 'chunk'}
                        selection={new Set<ChunkKey>()}
                        overlayVisible={claimsOverlayVisible}
                        selectable={false}
                        onOverlayVisibleChange={setClaimsOverlayVisible}
                        onRefresh={handleRefreshClaims}
                        onClusterHover={highlightClusters}
                        onClusterClick={handleClusterClick}
                        onClusterSelect={() => undefined}
                        onTeamHover={highlightClusters}
                        onTeamSelectInDim={() => undefined}
                      />
                    )}
                  </TabsContent>
                  <TabsContent value="players">
                    <PlayerLocationList
                      data={playerLocationsQ.data}
                      isLoading={playerLocationsQ.isLoading}
                      isError={playerLocationsQ.isError}
                      currentDimRelpath={regionRelpath}
                      dimensionLabelByRelpath={dimensionLabelByRelpath}
                      profilesByUuid={playerProfiles.profilesByUuid}
                      pendingProfileUuids={playerProfiles.pendingUuids}
                      onlinePlayerUuids={onlinePlayerUuids}
                      onlineOnly={onlinePlayersOnly}
                      onlineStatusLoading={onlinePlayersQ.isLoading}
                      onlineStatusAvailable={onlineStatusAvailable}
                      overlayVisible={playersOverlayVisible}
                      onOverlayVisibleChange={setPlayersOverlayVisible}
                      onOnlineOnlyChange={setOnlinePlayersOnly}
                      onRefresh={handleRefreshPlayers}
                      onPlayerClick={handlePlayerClick}
                    />
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {claimsPopover && popoverContext && (
        <ClusterPopover
          team={popoverContext.team}
          cluster={popoverContext.cluster}
          anchorEl={claimsPopover.anchorEl}
          mode={urlMode === 'regions' ? 'region' : 'chunk'}
          teamChunksInDim={popoverContext.teamChunksInDim}
          clustersInDim={popoverContext.clustersInDim}
          onClose={closeClaimsPopover}
          onSelectCluster={() => closeClaimsPopover()}
          onSelectTeamInDim={() => closeClaimsPopover()}
        />
      )}

      <MapInitDialog
        open={initOpen}
        serverId={serverId}
        force={initForce}
        onClose={() => {
          setInitOpen(false)
          setInitForce(false)
        }}
        onComplete={handleInitComplete}
      />
      {confirmDialog}
    </div>
  )
}

export default ServerChunkPrune
