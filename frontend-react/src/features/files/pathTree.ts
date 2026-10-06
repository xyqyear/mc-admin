export interface PathTreeNode<T> {
  key: string
  name: string
  isLeaf: boolean
  payload?: T
  children?: PathTreeNode<T>[]
}

export interface PathTreeEntry<T> {
  segments: { key: string; name: string }[]
  payload: T
}

export function buildPathTree<T>(entries: PathTreeEntry<T>[]): PathTreeNode<T>[] {
  const nodes = new Map<string, PathTreeNode<T>>()
  const roots: PathTreeNode<T>[] = []
  for (const { segments, payload } of entries) {
    for (const [index, { key, name }] of segments.entries()) {
      if (nodes.has(key)) continue
      const isLeaf = index === segments.length - 1
      const node: PathTreeNode<T> = { key, name, isLeaf, payload: isLeaf ? payload : undefined, children: isLeaf ? undefined : [] }
      nodes.set(key, node)
      const parentKey = segments[index - 1]?.key
      const parent = parentKey ? nodes.get(parentKey) : undefined
      if (parent) (parent.children ??= []).push(node)
      else roots.push(node)
    }
  }
  return roots
}

export function treeKeys<T>(nodes: PathTreeNode<T>[], leavesOnly = false): string[] {
  return nodes.flatMap(node => [
    ...(!leavesOnly || node.isLeaf ? [node.key] : []),
    ...treeKeys(node.children ?? [], leavesOnly),
  ])
}
