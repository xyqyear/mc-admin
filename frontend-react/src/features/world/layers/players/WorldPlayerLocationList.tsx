import type { WorldMapController } from '@/features/world/useWorldMapController'
import { PlayerLocationList } from '@/features/world/layers/players/PlayerLocationList'

interface WorldPlayerLocationListProps {
  players: WorldMapController['players']
  map: Pick<WorldMapController['map'], 'regionRelpath' | 'dimensionLabelByRelpath'>
}

export function WorldPlayerLocationList({ players, map }: WorldPlayerLocationListProps) {
  return (
    <PlayerLocationList
      data={players.playerLocationsQ.data}
      isLoading={players.playerLocationsQ.isLoading}
      isError={players.playerLocationsQ.isError}
      currentDimRelpath={map.regionRelpath}
      dimensionLabelByRelpath={map.dimensionLabelByRelpath}
      profilesByUuid={players.playerProfiles.profilesByUuid}
      pendingProfileUuids={players.playerProfiles.pendingUuids}
      profileError={players.playerProfiles.error}
      onRetryProfiles={players.playerProfiles.retry}
      onlinePlayerUuids={players.onlinePlayerUuids}
      onlineOnly={players.onlinePlayersOnly}
      onlineStatusLoading={players.onlinePlayersQ.isLoading}
      onlineStatusAvailable={players.onlineStatusAvailable}
      overlayVisible={players.playersOverlayVisible}
      onOverlayVisibleChange={players.setPlayersOverlayVisible}
      onOnlineOnlyChange={players.setOnlinePlayersOnly}
      onRefresh={players.handleRefreshPlayers}
      onPlayerClick={players.handlePlayerClick}
    />
  )
}
