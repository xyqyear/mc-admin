import { create } from 'zustand'

export type TaskCenterTab = 'background' | 'download'

interface TaskCenterState {
  isOpen: boolean
  activeTab: TaskCenterTab
  setOpen: (open: boolean) => void
  toggleOpen: () => void
  setActiveTab: (tab: TaskCenterTab) => void
}

export const useTaskCenterStore = create<TaskCenterState>()((set) => ({
  isOpen: false,
  activeTab: 'background',

  setOpen: (open) => set({ isOpen: open }),

  toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),

  setActiveTab: (tab) => set({ activeTab: tab }),
}))

// Selector hooks
export const useTaskCenterOpen = () =>
  useTaskCenterStore((state) => state.isOpen)

export const useTaskCenterActiveTab = () =>
  useTaskCenterStore((state) => state.activeTab)

export const useTaskCenterActions = () =>
  useTaskCenterStore((state) => ({
    setOpen: state.setOpen,
    toggleOpen: state.toggleOpen,
    setActiveTab: state.setActiveTab,
  }))
