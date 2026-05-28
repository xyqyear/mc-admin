import { useMutation, useQueryClient } from '@tanstack/react-query'
import { playerApi, type PlayerCleanupKind } from '@/hooks/api/playerApi'
import { queryKeys } from '@/utils/api'

export const usePlayerMutations = () => {
  const queryClient = useQueryClient()

  const useRefreshPlayerSkin = () => {
    return useMutation({
      mutationFn: (playerDbId: number) => playerApi.refreshPlayerSkin(playerDbId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.players.all })
      },
    })
  }

  const useDeletePlayerCleanup = () => {
    return useMutation({
      mutationFn: (kind: PlayerCleanupKind) => playerApi.deletePlayerCleanup(kind),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.players.all })
      },
    })
  }

  return {
    useDeletePlayerCleanup,
    useRefreshPlayerSkin,
  }
}
