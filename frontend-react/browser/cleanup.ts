type Cleanup = { label: string; run: () => Promise<unknown> }

export async function withCleanup<T>(body: () => Promise<T>, ...cleanups: Cleanup[]): Promise<T> {
  const failures: Array<{ label: string; error: unknown }> = []
  let result: T | undefined
  try {
    result = await body()
  } catch (error) {
    failures.push({ label: 'Original journey failure', error })
  }
  for (const cleanup of cleanups) {
    try {
      await cleanup.run()
    } catch (error) {
      failures.push({ label: `Cleanup failure (${cleanup.label})`, error })
    }
  }
  if (failures.length === 1) throw failures[0]!.error
  if (failures.length > 1) {
    const detail = failures.map(({ label, error }) => `${label}:\n${error instanceof Error ? error.stack ?? error.message : String(error)}`).join('\n\n')
    throw new AggregateError(failures.map(failure => failure.error), detail, { cause: failures[0]!.error })
  }
  return result as T
}
