import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface TokenStore {
  token: string | null
  setToken: (token: string) => void
  clearToken: () => void
}

export const useTokenStore = create<TokenStore>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token: string) => set({ token }),
      clearToken: () => set({ token: null }),
    }),
    {
      name: 'token',
    }
  )
)

// Helper hook to get hasToken as a reactive value
export const useHasToken = () => {
  const token = useTokenStore((state) => state.token)
  return token !== null
}
