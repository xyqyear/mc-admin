/**
 * Format file size from bytes to human readable format
 * @param bytes - File size in bytes
 * @returns Formatted file size string
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '-'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

/**
 * Format timestamp to localized date string
 * @param timestamp - Unix timestamp (in seconds) as number or string
 * @returns Formatted date string
 */
export function formatDate(timestamp: number | string): string {
  const ts = typeof timestamp === 'string' ? parseFloat(timestamp) : timestamp
  const date = new Date(ts * 1000)
  return date.toLocaleString('zh-CN')
}