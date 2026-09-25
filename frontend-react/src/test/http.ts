import { QueryClient } from '@tanstack/react-query'
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'

export function createTestClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  })
}

export function httpResponse(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  const response = { config, data, status, statusText: String(status), headers: {} }
  if (status >= 400) throw new AxiosError('请求失败', 'ERR_BAD_RESPONSE', config, undefined, response)
  return response
}

export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
