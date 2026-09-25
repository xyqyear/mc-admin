import { Map as MapIcon, RefreshCw } from 'lucide-react'
import React from 'react'
import { useParams } from 'react-router'
import { useWorldRestoreController } from '@/features/world/restore/useWorldRestoreController'

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
import MapHelpButton from '@/features/world/map/MapHelpButton'
import MapInitDialog from '@/features/world/map/MapInitDialog'
import ServerMap from '@/features/world/map/ServerMap'
import { ServerStopGuard } from '@/features/world/restore/components/ServerStopGuard'
import WorldRestoreSelectionPanel from '@/features/world/restore/components/WorldRestoreSelectionPanel'

const ServerWorldRestore: React.FC = () => {
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
    openInitDialog,
    handleInitComplete,
    handleInitClose,
    handleRefreshMap,
    initialView,
    regionRelpath,
    rootList,
    dimensionOptions,
    dimensionLabelByRelpath,
    dimensionSelectValue,
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
    modeChangeConfirmDialog,
    handleSelectionChange,
    handleModeChange,
    handleClusterSelect,
    handleTeamSelectInDim,
    selectionMode,
    selection
  } = useWorldRestoreController(serverId)

  if (!serverId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>错误</AlertTitle>
        <AlertDescription>缺少服务器ID</AlertDescription>
      </Alert>
    )
  }


  return (
    <div className="flex flex-col gap-4 h-full">
      <PageHeader
        title="地图回档"
        icon={<MapIcon className="w-5 h-5" />}
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
                      onClick={() => openInitDialog(true)}
                      title="删除客户端 JAR 和调色板缓存后重新下载并生成"
                    >
                      重载渲染前置
                    </Button>
                    <Tabs
                      value={urlMode}
                      onValueChange={(v) => {
                        if (v === 'chunk' || v === 'region')
                          handleModeChange(v)
                      }}
                    >
                      <TabsList>
                        <TabsTrigger value="region" className="px-3">
                          区域选择
                        </TabsTrigger>
                        <TabsTrigger value="chunk" className="px-3">
                          区块选择
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                  </>
                )}
                <Select
                  items={dimensionOptions}
                  value={dimensionSelectValue}
                  onValueChange={(v) => {
                    if (typeof v === 'string') handleDimensionChange(v)
                  }}
                  itemToStringLabel={(v) =>
                    dimensionOptions.find((o) => o.value === v)?.label ?? String(v)
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
                <MapHelpButton />
              </>
            ) : null}
            <ServerOperationButtons
              serverId={serverId}
              serverName={serverInfoQ.data?.name ?? serverId}
              status={statusQ.data}
              showReturnButton={false}
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

      {mapStatusQ.isError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取地图初始化状态</AlertDescription>
        </Alert>
      )}

      {!mapStatusQ.isLoading && mapStatusQ.data && !mapInitialized && (
        <Card>
          <CardContent className="py-8 flex flex-col items-center gap-4">
            <div className="text-center text-muted-foreground">
              {!mapStatusQ.data.client_jar_present
                ? '尚未下载客户端 JAR。'
                : !mapStatusQ.data.palette_present
                  ? '尚未生成调色板。'
                  : '调色板已过期（版本或mods变更）。'}
            </div>
            <Button onClick={() => openInitDialog(false)}>初始化地图</Button>
          </CardContent>
        </Card>
      )}

      <ServerStopGuard status={statusQ.data} />

      {(mapInitialized || layoutQ.isLoading) && (
        <div className="flex flex-col gap-4 md:flex-1 md:min-h-0 md:grid md:grid-cols-[1fr_270px] md:grid-rows-1">
          <Card className="overflow-hidden py-0">
            <CardContent className="p-0 h-[60vh] md:h-full md:min-h-[60vh]">
              {regionsMap && regionRelpath ? (
                <ServerMap
                  serverId={serverId}
                  regionPath={regionRelpath}
                  regions={regionsMap}
                  selectionMode={selectionMode}
                  selection={selection}
                  onSelectionChange={handleSelectionChange}
                  overlays={mapOverlays}
                  initialView={initialView}
                  onViewChange={handleViewChange}
                />
              ) : layoutQ.isLoading || regionsLoading ? (
                <div className="h-[60vh] md:h-full flex items-center justify-center">
                  <Spinner />
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex flex-col min-w-0 md:min-h-0 md:overflow-y-auto md:*:shrink-0">
            <Card>
              <CardContent>
                {mapInitialized ? (
                  <Tabs defaultValue="backup" className="gap-4">
                    <TabsList
                      className={
                        claimsAvailable
                          ? 'grid w-full grid-cols-3'
                          : 'grid w-full grid-cols-2'
                      }
                    >
                      <TabsTrigger value="backup">备份与恢复</TabsTrigger>
                      {claimsAvailable && (
                        <TabsTrigger value="claims">领地列表</TabsTrigger>
                      )}
                      <TabsTrigger value="players">玩家位置</TabsTrigger>
                    </TabsList>
                    <TabsContent value="backup">
                      <WorldRestoreSelectionPanel
                        serverId={serverId}
                        regionDirRelpath={regionRelpath}
                        selection={selection}
                        mode={urlMode}
                        serverStopped={serverStopped}
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
                          mode={urlMode}
                          selection={selection}
                          overlayVisible={claimsOverlayVisible}
                          onOverlayVisibleChange={setClaimsOverlayVisible}
                          onRefresh={handleRefreshClaims}
                          onClusterHover={highlightClusters}
                          onClusterClick={handleClusterClick}
                          onClusterSelect={handleClusterSelect}
                          onTeamHover={highlightClusters}
                          onTeamSelectInDim={handleTeamSelectInDim}
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
                ) : (
                  <WorldRestoreSelectionPanel
                    serverId={serverId}
                    regionDirRelpath={regionRelpath}
                    selection={selection}
                    mode={urlMode}
                    serverStopped={serverStopped}
                  />
                )}
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
          mode={urlMode}
          teamChunksInDim={popoverContext.teamChunksInDim}
          clustersInDim={popoverContext.clustersInDim}
          onClose={closeClaimsPopover}
          onSelectCluster={() => {
            handleClusterSelect(popoverContext.cluster)
            closeClaimsPopover()
          }}
          onSelectTeamInDim={() => {
            handleTeamSelectInDim(popoverContext.team)
            closeClaimsPopover()
          }}
        />
      )}

      <MapInitDialog
        open={initOpen}
        serverId={serverId}
        force={initForce}
        onClose={handleInitClose}
        onComplete={handleInitComplete}
      />
      {modeChangeConfirmDialog}
    </div>
  )
}

export default ServerWorldRestore
