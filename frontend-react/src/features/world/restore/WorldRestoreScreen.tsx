import { Map as MapIcon, RefreshCw } from 'lucide-react'
import React from 'react'
import { useParams } from 'react-router'
import { useWorldRestoreController } from '@/features/world/restore/useWorldRestoreController'

import PageHeader from '@/shared/layout/PageHeader'
import ServerOperationButtons from '@/features/servers/ui/ServerOperationButtons'
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Card, CardContent } from '@/shared/ui/card'
import { Skeleton } from '@/shared/ui/skeleton'
import { Spinner } from '@/shared/ui/spinner'
import { Tabs, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { cn } from '@/shared/lib/utils'
import { ClusterPopover } from '@/features/world/layers/claims/ClusterPopover'
import { TeamClusterList } from '@/features/world/layers/claims/TeamClusterList'
import { WorldPlayerLocationList } from '@/features/world/layers/players/WorldPlayerLocationList'
import { WorldDimensionSelect } from '@/features/world/map/WorldDimensionSelect'
import { WorldMapInitialization } from '@/features/world/map/WorldMapInitialization'
import MapHelpButton from '@/features/world/map/MapHelpButton'
import MapInitDialog from '@/features/world/map/MapInitDialog'
import ServerMap from '@/features/world/map/ServerMap'
import { ServerStopGuard } from '@/features/world/restore/components/ServerStopGuard'
import WorldRestoreSelectionPanel from '@/features/world/restore/components/WorldRestoreSelectionPanel'
import { WorldRestoreSidebar } from '@/features/world/restore/components/WorldRestoreSidebar'

const ServerWorldRestore: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const serverId = id ?? ''
  const { map, server, claims, players,
    urlMode, modeChangeConfirmDialog, handleSelectionChange, handleModeChange, handleClusterSelect, handleTeamSelectInDim, selectionMode, selection,
  } = useWorldRestoreController(serverId)
  const { popoverContext } = claims

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
            {map.layoutQ.isLoading ? (
              <>
                <Skeleton className="h-9 w-30" />
                <Skeleton className="h-9 w-65" />
              </>
            ) : map.dimensionOptions.length > 0 ? (
              <>
                {map.mapInitialized && (
                  <>
                    <Button
                      variant="outline"
                      onClick={map.handleRefreshMap}
                      title="重新读取世界元数据并刷新瓦片"
                    >
                      <RefreshCw className="mr-1 h-4 w-4" />
                      刷新地图
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={() => map.openInitDialog(true)}
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
                <WorldDimensionSelect options={map.dimensionOptions} value={map.dimensionSelectValue} onChange={map.handleDimensionChange} />
                <MapHelpButton />
              </>
            ) : null}
            <ServerOperationButtons
              serverId={serverId}
              serverName={server.serverInfoQ.data?.name ?? serverId}
              status={server.statusQ.data}
              showReturnButton={false}
            />
          </>
        }
      />

      {map.layoutQ.isError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取世界布局</AlertDescription>
        </Alert>
      )}

      {!map.layoutQ.isLoading && map.layoutQ.data && map.rootList.length === 0 && (
        <Alert>
          <AlertTitle>未发现世界</AlertTitle>
          <AlertDescription>
            该服务器的 data/ 目录下没有可识别的世界根（缺少 level.dat）。
          </AlertDescription>
        </Alert>
      )}

      {map.regionsError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取该维度的区域清单</AlertDescription>
        </Alert>
      )}

      <WorldMapInitialization map={map} showStatusError />

      <ServerStopGuard status={server.statusQ.data} />

      <div
        className={cn('flex flex-col gap-4', (map.mapInitialized || map.layoutQ.isLoading)
          ? 'md:flex-1 md:min-h-0 md:grid md:grid-cols-[1fr_270px] md:grid-rows-1'
          : 'md:w-67.5')}
      >
        {(map.mapInitialized || map.layoutQ.isLoading) && (
          <Card className="overflow-hidden py-0">
            <CardContent className="p-0 h-[60vh] md:h-full md:min-h-[60vh]">
              {map.regionsMap && map.regionRelpath ? (
                <ServerMap
                  serverId={serverId}
                  regionPath={map.regionRelpath}
                  regions={map.regionsMap}
                  selectionMode={selectionMode}
                  selection={selection}
                  onSelectionChange={handleSelectionChange}
                  overlays={map.mapOverlays}
                  initialView={map.initialView}
                  onViewChange={map.handleViewChange}
                />
              ) : map.layoutQ.isLoading || map.regionsLoading ? (
                <div className="h-[60vh] md:h-full flex items-center justify-center">
                  <Spinner />
                </div>
              ) : null}
            </CardContent>
          </Card>
        )}
        <WorldRestoreSidebar
          mapInitialized={map.mapInitialized}
          backup={
            <WorldRestoreSelectionPanel
              serverId={serverId}
              regionDirRelpath={map.regionRelpath}
              selection={selection}
              mode={urlMode}
              serverStopped={server.serverStopped}
            />
          }
          claims={claims.claimsAvailable ? (
            <TeamClusterList
              data={claims.claimsQ.data}
              isLoading={claims.claimsQ.isLoading}
              isError={claims.claimsQ.isError}
              currentDimRelpath={map.regionRelpath}
              dimensionLabelByRelpath={map.dimensionLabelByRelpath}
              mode={urlMode}
              selection={selection}
              overlayVisible={claims.claimsOverlayVisible}
              onOverlayVisibleChange={claims.setClaimsOverlayVisible}
              onRefresh={claims.handleRefreshClaims}
              onClusterHover={claims.highlightClusters}
              onClusterClick={claims.handleClusterClick}
              onClusterSelect={handleClusterSelect}
              onTeamHover={claims.highlightClusters}
              onTeamSelectInDim={handleTeamSelectInDim}
            />
          ) : undefined}
          players={
            <WorldPlayerLocationList players={players} map={map} />
          }
        />
      </div>

      {claims.claimsPopover && popoverContext && (
        <ClusterPopover
          team={popoverContext.team}
          cluster={popoverContext.cluster}
          anchorEl={claims.claimsPopover.anchorEl}
          mode={urlMode}
          teamChunksInDim={popoverContext.teamChunksInDim}
          clustersInDim={popoverContext.clustersInDim}
          onClose={claims.closeClaimsPopover}
          onSelectCluster={() => {
            handleClusterSelect(popoverContext.cluster)
            claims.closeClaimsPopover()
          }}
          onSelectTeamInDim={() => {
            handleTeamSelectInDim(popoverContext.team)
            claims.closeClaimsPopover()
          }}
        />
      )}

      <MapInitDialog
        open={map.initOpen}
        serverId={serverId}
        force={map.initForce}
        onClose={map.handleInitClose}
        onComplete={map.handleInitComplete}
      />
      {modeChangeConfirmDialog}
    </div>
  )
}

export default ServerWorldRestore
