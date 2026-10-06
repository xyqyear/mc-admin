export function normalizeUuid(value: string | null | undefined): string | null {
  if (!value) return null
  const normalized = value.replaceAll('-', '').toLowerCase()
  return /^[0-9a-f]{32}$/.test(normalized) ? normalized : null
}
