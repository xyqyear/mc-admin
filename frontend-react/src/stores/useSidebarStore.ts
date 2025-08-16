import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SidebarStore {
  openKeys: string[]
  lastPath: string | null
  setOpenKeys: (keys: string[]) => void
  updateForNavigation: (pathname: string) => void
  addOpenKey: (key: string) => void
  removeOpenKey: (key: string) => void
}

export const useSidebarStore = create<SidebarStore>()(
  persist(
    (set, get) => ({
      openKeys: ['服务器管理'], // Default open keys
      lastPath: null,
      setOpenKeys: (keys: string[]) => set({ openKeys: keys }),
      updateForNavigation: (pathname: string) => {
        const { lastPath } = get()
        // Only auto-update if this is a real navigation (path changed)
        if (lastPath !== pathname) {
          const newOpenKeys = getOpenKeysFromPath(pathname)
          set({ openKeys: newOpenKeys, lastPath: pathname })
        }
      },
      addOpenKey: (key: string) => {
        const { openKeys } = get()
        if (!openKeys.includes(key)) {
          set({ openKeys: [...openKeys, key] })
        }
      },
      removeOpenKey: (key: string) => {
        const { openKeys } = get()
        set({ openKeys: openKeys.filter(k => k !== key) })
      },
    }),
    {
      name: 'sidebar-state',
    }
  )
)

// Helper function to get open keys based on current path
export const getOpenKeysFromPath = (pathname: string): string[] => {
  const openKeys: string[] = []
  
  // Check if we're on a server-specific page
  const serverMatch = pathname.match(/^\/server\/([^\/]+)/)
  if (serverMatch) {
    const serverId = serverMatch[1]
    if (serverId !== 'new') {
      // Always include the main server management menu
      openKeys.push('服务器管理')
      // Add the specific server submenu
      openKeys.push(serverId)
    } else {
      // For new server page, just open the main server menu
      openKeys.push('服务器管理')
    }
  } else if (pathname === '/overview' || pathname === '/backups') {
    // For other main pages, don't open any submenus by default
    // User can manually open them if needed
  } else if (pathname === '/') {
    // For home page, don't open any submenus by default
  } else {
    // For any other server-related pages, try to open server management
    if (pathname.includes('/server/')) {
      openKeys.push('服务器管理')
    }
  }
  
  return openKeys
}
