import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface SidebarStore {
  openKeys: string[];
  lastPath: string | null;
  collapsed: boolean;
  setOpenKeys: (keys: string[]) => void;
  updateForNavigation: (pathname: string) => void;
  addOpenKey: (key: string) => void;
  removeOpenKey: (key: string) => void;
  toggleCollapsed: () => void;
  setCollapsed: (collapsed: boolean) => void;
}

export const useSidebarStore = create<SidebarStore>()(
  persist(
    (set, get) => ({
      openKeys: ["服务器管理"],
      lastPath: null,
      collapsed: false,
      setOpenKeys: (keys: string[]) => set({ openKeys: keys }),
      updateForNavigation: (pathname: string) => {
        const { lastPath } = get();
        // Skip when the path is unchanged so user toggles aren't clobbered by re-renders.
        if (lastPath !== pathname) {
          const newOpenKeys = getOpenKeysFromPath(pathname);
          set({ openKeys: newOpenKeys, lastPath: pathname });
        }
      },
      addOpenKey: (key: string) => {
        const { openKeys } = get();
        if (!openKeys.includes(key)) {
          set({ openKeys: [...openKeys, key] });
        }
      },
      removeOpenKey: (key: string) => {
        const { openKeys } = get();
        set({ openKeys: openKeys.filter((k) => k !== key) });
      },
      toggleCollapsed: () => {
        const { collapsed } = get();
        set({ collapsed: !collapsed });
      },
      setCollapsed: (collapsed: boolean) => set({ collapsed }),
    }),
    {
      name: "mc-admin-sidebar",
      storage: createJSONStorage(() => localStorage),
      version: 1,
    }
  )
);

export const useSidebarOpenKeys = () =>
  useSidebarStore((state) => state.openKeys);

export const useSidebarCollapsed = () =>
  useSidebarStore((state) => state.collapsed);

export const getOpenKeysFromPath = (pathname: string): string[] => {
  const openKeys: string[] = [];

  const serverMatch = pathname.match(/^\/server\/([^/]+)/);
  if (serverMatch) {
    const serverId = serverMatch[1];
    if (serverId !== "new") {
      openKeys.push("服务器管理");
      openKeys.push(serverId);
    } else {
      openKeys.push("服务器管理");
    }
  } else if (pathname.startsWith("/admin/")) {
    openKeys.push("超管");
  } else if (pathname === "/overview" || pathname === "/backups") {
    // Top-level pages with no submenu by default.
  } else if (pathname === "/") {
    // Self-check page leaves submenus collapsed.
  } else {
    if (pathname.includes("/server/")) {
      openKeys.push("服务器管理");
    }
  }

  return openKeys;
};
