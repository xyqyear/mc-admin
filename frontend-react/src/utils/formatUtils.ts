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

/**
 * Cached Intl.Collator instance for natural sorting
 * Reusing the same instance improves performance significantly
 */
const naturalCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: 'base'
});

/**
 * Natural compare function for sorting strings with numbers
 * Ensures that "9.txt" comes before "10.txt" instead of after it
 * Uses a cached Collator instance for optimal performance
 * @param a - First string to compare
 * @param b - Second string to compare
 * @returns Comparison result (-1, 0, or 1)
 *
 * @example
 * ['1.txt', '10.txt', '2.txt'].sort(naturalCompare)
 * // Returns: ['1.txt', '2.txt', '10.txt']
 */
export function naturalCompare(a: string, b: string): number {
  return naturalCollator.compare(a, b);
}

/**
 * Format Minecraft player UUID to standard UUID format with dashes
 * Converts 32-character hex string to standard 8-4-4-4-12 UUID format
 * @param uuid - UUID string without dashes (32 characters)
 * @returns Formatted UUID string with dashes
 *
 * @example
 * formatUUID('a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6')
 * // Returns: 'a1b2c3d4-e5f6-a7b8-c9d0-e1f2a3b4c5d6'
 */
export function formatUUID(uuid: string): string {
  if (!uuid || uuid.length !== 32) {
    return uuid; // Return as-is if invalid
  }

  // Format: 8-4-4-4-12
  return `${uuid.substring(0, 8)}-${uuid.substring(8, 12)}-${uuid.substring(12, 16)}-${uuid.substring(16, 20)}-${uuid.substring(20, 32)}`;
}

