export const taskQueryKeys = {
  all: ['tasks'] as const,
  list: (params?: object) => [...taskQueryKeys.all, params] as const,
  active: () => [...taskQueryKeys.all, 'active'] as const,
  detail: (taskId: string) => [...taskQueryKeys.all, taskId] as const,
  events: () => [...taskQueryKeys.all, 'events'] as const,
}
