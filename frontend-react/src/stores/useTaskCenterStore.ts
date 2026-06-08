import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { useShallow } from 'zustand/shallow'

import {
  DEFAULT_TASK_CENTER_TRIGGER_POSITION,
  type TaskCenterTriggerPosition,
} from '@/config/taskCenterLayout'

export type TaskCenterTab = 'background' | 'download'

interface TaskCenterState {
  isOpen: boolean
  activeTab: TaskCenterTab
  triggerPosition: TaskCenterTriggerPosition
  setOpen: (open: boolean) => void
  toggleOpen: () => void
  setActiveTab: (tab: TaskCenterTab) => void
  setTriggerPosition: (position: TaskCenterTriggerPosition) => void
}

export const useTaskCenterStore = create<TaskCenterState>()(
  persist(
    (set) => ({
      isOpen: false,
      activeTab: 'background',
      triggerPosition: DEFAULT_TASK_CENTER_TRIGGER_POSITION,

      setOpen: (open) => set({ isOpen: open }),

      toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),

      setActiveTab: (tab) => set({ activeTab: tab }),

      setTriggerPosition: (position) => set({ triggerPosition: position }),
    }),
    {
      name: 'mc-admin-task-center',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        triggerPosition: state.triggerPosition,
      }),
    }
  )
)

export const useTaskCenterOpen = () =>
  useTaskCenterStore((state) => state.isOpen)

export const useTaskCenterActiveTab = () =>
  useTaskCenterStore((state) => state.activeTab)

export const useTaskCenterTriggerPosition = () =>
  useTaskCenterStore((state) => state.triggerPosition)

export const useTaskCenterActions = () =>
  useTaskCenterStore(
    useShallow((state) => ({
      setOpen: state.setOpen,
      toggleOpen: state.toggleOpen,
      setActiveTab: state.setActiveTab,
      setTriggerPosition: state.setTriggerPosition,
    }))
  )
