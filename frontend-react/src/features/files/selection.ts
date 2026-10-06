export function searchResultPath(searchPath: string, resultPath: string): string {
  return '/' + [searchPath, resultPath].flatMap(path => path.split('/').filter(Boolean)).join('/')
}

export function includesFilePath(parent: string, path: string): boolean {
  const root = parent.replace(/\/+$/, '')
  return path === root || path.startsWith(root + '/')
}
