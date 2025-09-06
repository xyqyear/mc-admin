/**
 * Format file size from bytes to human readable format
 * @param bytes - File size in bytes
 * @returns Formatted file size string
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "-";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

/**
 * Format timestamp to localized date string
 * @param timestamp - Unix timestamp (in seconds) as number or string
 * @returns Formatted date string
 */
export function formatDate(timestamp: number | string): string {
  const ts = typeof timestamp === "string" ? parseFloat(timestamp) : timestamp;
  const date = new Date(ts * 1000);
  return date.toLocaleString("zh-CN");
}

/**
 * Format ISO datetime string to Chinese locale format
 * @param timeString - ISO datetime string (e.g., "2024-01-26T05:07:03Z")
 * @returns Formatted date string in Chinese locale
 */
export function formatDateTime(timeString: string): string {
  return new Date(timeString).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
