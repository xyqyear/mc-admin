import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

interface TokenStore {
  token: string | null
  setToken: (token: string) => void
  clearToken: () => void
  isAuthenticated: () => boolean
}

export const useTokenStore = create<TokenStore>()(
  persist(
    (set, get) => ({
      token: null,
      setToken: (token: string) => {
        if (!token || token.trim() === '') {
          console.warn('Attempted to set empty or invalid token')
          return
        }
        set({ token: token.trim() })
      },
      clearToken: () => set({ token: null }),
      isAuthenticated: () => {
        const { token } = get()
        return token !== null && token.trim() !== ''
      },
    }),
    {
      name: 'mc-admin-token',
      storage: createJSONStorage(() => localStorage),
      // Version for migration handling
      version: 1,
    }
  )
)

// Selector hooks for better performance
export const useIsAuthenticated = () => 
  useTokenStore((state) => state.isAuthenticated())

export const useToken = () => 
  useTokenStore((state) => state.token)

// Legacy compatibility - deprecated, use useIsAuthenticated instead
export const useHasToken = useIsAuthenticated
