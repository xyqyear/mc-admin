export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "-";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

// `timestamp` is Unix epoch seconds.
export function formatDate(timestamp: number | string): string {
  const ts = typeof timestamp === "string" ? parseFloat(timestamp) : timestamp;
  const date = new Date(ts * 1000);
  return date.toLocaleString("zh-CN");
}

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

// Reused across many sorts; the Collator constructor is comparatively expensive.
const naturalCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: 'base'
});

// Sorts "9.txt" before "10.txt" (numeric-aware compare).
export function naturalCompare(a: string, b: string): number {
  return naturalCollator.compare(a, b);
}

// Inserts dashes into a 32-char hex UUID (Mojang's compact form) to produce the canonical 8-4-4-4-12 layout.
export function formatUUID(uuid: string): string {
  if (!uuid || uuid.length !== 32) {
    return uuid;
  }

  return `${uuid.substring(0, 8)}-${uuid.substring(8, 12)}-${uuid.substring(12, 16)}-${uuid.substring(16, 20)}-${uuid.substring(20, 32)}`;
}

