import { useMutation, useQueryClient } from '@tanstack/react-query'
import { playerApi } from '@/hooks/api/playerApi'
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

  return {
    useRefreshPlayerSkin,
  }
}
