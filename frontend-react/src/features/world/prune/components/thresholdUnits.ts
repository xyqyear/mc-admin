export type ThresholdUnit = 'seconds' | 'minutes' | 'hours'

export const secondsToThresholdInput = (
  seconds: number,
): { value: string; unit: ThresholdUnit } => {
  if (seconds > 0 && seconds % 3600 === 0) {
    return { value: String(seconds / 3600), unit: 'hours' }
  }
  if (seconds > 0 && seconds % 60 === 0) {
    return { value: String(seconds / 60), unit: 'minutes' }
  }
  return { value: String(seconds), unit: 'seconds' }
}

export const thresholdInputToSeconds = (
  value: string,
  unit: ThresholdUnit,
): number => {
  const numeric = Number(value)
  const safe = Number.isFinite(numeric) && numeric > 0 ? numeric : 0
  if (unit === 'hours') return Math.round(safe * 3600)
  if (unit === 'minutes') return Math.round(safe * 60)
  return Math.round(safe)
}
