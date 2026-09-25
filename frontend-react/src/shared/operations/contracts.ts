export interface Operation {
  operation_id: string
  kind: string
  legacy_id: string | null
  state: string
  data_changed: boolean
  failure_code: string | null
  resources: { kind: string; server_id: string | null; generation: number | null; path: string }[]
}

export const isTerminalOperation = (operation: Operation) =>
  ['succeeded', 'failed', 'cancelled', 'interrupted', 'skipped'].includes(operation.state)
