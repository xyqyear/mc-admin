import { useMutation, useQueryClient } from '@tanstack/react-query'
import { playerApi } from '@/features/players/api';
import type { PlayerCleanupKind } from '@/features/players/contracts';
import { queryKeys } from '@/shared/http/api'
export const useRefreshPlayerSkin = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (playerDbId: number) => playerApi.refreshPlayerSkin(playerDbId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.players.all })
    },
  })
}

export const useDeletePlayerCleanup = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (kind: PlayerCleanupKind) => playerApi.deletePlayerCleanup(kind),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.players.all })
    },
  })
}
