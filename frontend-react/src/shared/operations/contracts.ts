export interface Operation {
  operation_id: string
  kind: string
  state: string
  data_changed: boolean
  updated_at: string
  ended_at: string | null
  resources: { kind: string; server_id: string | null; generation: number | null; path: string }[]
}

export interface OperationChange extends Operation { sequence: number }

export interface OperationChanges {
  items: OperationChange[]
  next_cursor: string
  has_more: boolean
  active_count: number
  reset_required: boolean
}

export const isTerminalOperation = (operation: Operation) =>
  ['succeeded', 'failed', 'cancelled', 'interrupted', 'skipped'].includes(operation.state)
