import type { SearchFileItem } from './contracts'
import { searchResultPath } from './selection'

export type FileNavigationDestination = [path: string, query?: string, regex?: boolean]

export function fileNavigationHref(
  location: { pathname: string; search: string },
  path: string,
  query = '',
  regex = false,
): string {
  const params = new URLSearchParams(location.search)
  if (path === '/') params.delete('path'); else params.set('path', path)
  if (query.trim()) params.set('q', query); else params.delete('q')
  if (regex) params.set('regex', 'true'); else params.delete('regex')
  const search = params.toString()
  return `${location.pathname}${search ? `?${search}` : ''}`
}

export function searchResultDestination(
  searchPath: string,
  key: string,
  currentRegex: string,
  item?: Pick<SearchFileItem, 'name' | 'type'>,
): FileNavigationDestination {
  const path = searchResultPath(searchPath, key)
  if (!item) return [path, currentRegex, true]
  if (item.type === 'directory') return [path]
  return [path.slice(0, path.lastIndexOf('/')) || '/', item.name]
}
