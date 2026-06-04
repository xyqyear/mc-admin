import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router'

export type HashUrlParamsUpdater = (params: URLSearchParams) => void

interface UseHashUrlParamsOptions {
  migrateSearchParams?: boolean
}

function parseHashParams(hash: string): URLSearchParams {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  return new URLSearchParams(raw.startsWith('?') ? raw.slice(1) : raw)
}

function readUrlParams(
  keys: readonly string[],
  search: string,
  hash: string,
): URLSearchParams {
  const params = new URLSearchParams(search)
  const hashParams = parseHashParams(hash)
  for (const key of keys) {
    const value = hashParams.get(key)
    if (value !== null) params.set(key, value)
  }
  return params
}

function ownedParamsEqual(
  keys: readonly string[],
  a: URLSearchParams,
  b: URLSearchParams,
): boolean {
  return keys.every((key) => a.get(key) === b.get(key))
}

function hasOwnedSearchParams(keys: readonly string[], search: string): boolean {
  const params = new URLSearchParams(search)
  return keys.some((key) => params.has(key))
}

function hashFromParams(
  keys: readonly string[],
  params: URLSearchParams,
  currentHash: string,
): string {
  const hashParams = parseHashParams(currentHash)
  for (const key of keys) {
    const value = params.get(key)
    if (value !== null) hashParams.set(key, value)
    else hashParams.delete(key)
  }
  const serialized = hashParams.toString()
  return serialized ? `#${serialized}` : ''
}

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`
}

function urlFromParams(
  keys: readonly string[],
  params: URLSearchParams,
  stripSearchParams: boolean,
): string {
  const url = new URL(window.location.href)
  if (stripSearchParams) {
    for (const key of keys) {
      url.searchParams.delete(key)
    }
  }
  url.hash = hashFromParams(keys, params, window.location.hash)
  return `${url.pathname}${url.search}${url.hash}`
}

function replaceHashUrlParamsValue(
  keys: readonly string[],
  params: URLSearchParams,
): void {
  const nextUrl = urlFromParams(keys, params, false)
  if (nextUrl === currentPath()) return
  window.location.replace(nextUrl)
}

function canonicalizeSearchParams(
  keys: readonly string[],
  params: URLSearchParams,
): void {
  const nextUrl = urlFromParams(keys, params, true)
  if (nextUrl === currentPath()) return
  window.history.replaceState(window.history.state, '', nextUrl)
}

export function useHashUrlParams(
  keys: readonly string[],
  options: UseHashUrlParamsOptions = {},
): readonly [URLSearchParams, (update: HashUrlParamsUpdater) => void] {
  const location = useLocation()
  const { migrateSearchParams = true } = options
  const [params, setParams] = useState(() =>
    readUrlParams(keys, location.search, location.hash),
  )

  useEffect(() => {
    const syncFromUrl = () => {
      const next = readUrlParams(
        keys,
        window.location.search,
        window.location.hash,
      )
      setParams((current) =>
        ownedParamsEqual(keys, current, next) ? current : next,
      )
    }
    syncFromUrl()
    window.addEventListener('hashchange', syncFromUrl)
    return () => window.removeEventListener('hashchange', syncFromUrl)
  }, [keys, location.pathname, location.search, location.hash])

  useEffect(() => {
    if (!migrateSearchParams) return
    if (!hasOwnedSearchParams(keys, window.location.search)) return
    const next = readUrlParams(
      keys,
      window.location.search,
      window.location.hash,
    )
    canonicalizeSearchParams(keys, next)
    setParams((current) =>
      ownedParamsEqual(keys, current, next) ? current : next,
    )
  }, [
    keys,
    location.pathname,
    location.search,
    location.hash,
    migrateSearchParams,
  ])

  const replaceParams = useCallback(
    (update: HashUrlParamsUpdater) => {
      const next = readUrlParams(
        keys,
        window.location.search,
        window.location.hash,
      )
      update(next)
      replaceHashUrlParamsValue(keys, next)
      setParams((current) =>
        ownedParamsEqual(keys, current, next) ? current : next,
      )
    },
    [keys],
  )

  return [params, replaceParams] as const
}

export function readHashUrlParams(keys: readonly string[]): URLSearchParams {
  return readUrlParams(keys, window.location.search, window.location.hash)
}

export function replaceHashUrlParams(
  keys: readonly string[],
  update: HashUrlParamsUpdater,
): void {
  const next = readHashUrlParams(keys)
  update(next)
  replaceHashUrlParamsValue(keys, next)
}
