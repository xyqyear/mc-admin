import { queryOptions, useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { compareVersions } from './config'
import { queryKeys } from '@/shared/http/api'

const versionPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][\da-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][\da-zA-Z-]*))*)?$/
const releaseSchema = z.array(z.strictObject({
  version: z.string().regex(versionPattern),
  date: z.iso.date(),
  title: z.string().min(1),
  description: z.string(),
  features: z.array(z.string()).optional(),
  fixes: z.array(z.string()).optional(),
  improvements: z.array(z.string()).optional(),
})).min(1).refine(entries => new Set(entries.map(entry => entry.version)).size === entries.length)

export function parseReleaseData(value: unknown) {
  const versionUpdates = releaseSchema.parse(value)
  const currentVersion = versionUpdates.reduce((latest, entry) =>
    compareVersions(entry.version, latest.version) > 0 ? entry : latest,
  ).version
  return { versionUpdates, currentVersion }
}

export const releaseDataOptions = queryOptions({
  queryKey: queryKeys.release(),
  queryFn: async ({ signal }) => {
    const response = await fetch('/static/release.json', { cache: 'no-store', signal })
    if (!response.ok) throw new Error('版本信息加载失败')
    try {
      return parseReleaseData(await response.json())
    } catch {
      throw new Error('版本信息格式错误')
    }
  },
  staleTime: Infinity,
  gcTime: Infinity,
  retry: false,
})

export function useReleaseData() {
  return useQuery(releaseDataOptions)
}
