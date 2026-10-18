import { expect, it } from 'vitest'
import { fileNavigationHref, searchResultDestination } from './navigation'

it('encodes a literal filename and its captured parent while retaining unrelated query state', () => {
  const destination = searchResultDestination(
    '/captured root', '/配置/数据 #&+.7z', 'old.*pattern',
    { name: '数据 #&+.7z', type: 'file' },
  )
  const href = fileNavigationHref(
    { pathname: '/server/alpha/files', search: '?path=%2Fold&q=draft&regex=true&view=list' },
    ...destination,
  )
  const url = new URL(href, 'https://example.test')
  expect(url.pathname).toBe('/server/alpha/files')
  expect(url.searchParams.get('path')).toBe('/captured root/配置')
  expect(url.searchParams.get('q')).toBe('数据 #&+.7z')
  expect(url.searchParams.has('regex')).toBe(false)
  expect(url.searchParams.get('view')).toBe('list')
})

it('clears directory filters and omits the server root while preserving other URL parameters', () => {
  const destination = searchResultDestination('/', '/', 'stale.*', { name: '/', type: 'directory' })
  expect(fileNavigationHref(
    { pathname: '/server/alpha/files', search: '?path=%2Fold&q=stale&regex=true&view=list' },
    ...destination,
  )).toBe('/server/alpha/files?view=list')
})

it('retains the executed expression for a structural directory without treating it as a real result', () => {
  const destination = searchResultDestination('/captured', '/virtual', '^配置[.]toml$')
  const url = new URL(fileNavigationHref(
    { pathname: '/server/alpha/files', search: '' }, ...destination,
  ), 'https://example.test')
  expect(url.searchParams.get('path')).toBe('/captured/virtual')
  expect(url.searchParams.get('q')).toBe('^配置[.]toml$')
  expect(url.searchParams.get('regex')).toBe('true')
})
