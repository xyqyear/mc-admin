import { useState } from 'react'

export interface ConfigurationSnapshot<T> {
  version: string
  value: T
  description: string
  readAt?: number
}

export function useConfigurationSession<T>(remote: ConfigurationSnapshot<T>, followRemoteWhenUntouched = false) {
  const [baseline, setBaseline] = useState(remote)
  const [draft, setDraftValue] = useState(remote.value)
  const [authored, setAuthored] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [previousRead, setPreviousRead] = useState<{ version: string; readAt?: number } | null>(null)
  const waitingForAppliedRead = previousRead?.version === remote.version && previousRead?.readAt === remote.readAt
  const changed = baseline.version !== remote.version && !waitingForAppliedRead

  if (followRemoteWhenUntouched && changed && !conflict && !authored) {
    setBaseline(remote)
    setDraftValue(remote.value)
    setPreviousRead(null)
  }

  return {
    baseline, draft, remote,
    setDraft: (value: T) => {
      if (JSON.stringify(value) !== JSON.stringify(baseline.value)) setAuthored(true)
      setDraftValue(value)
    },
    needsComparison: conflict || changed,
    canSubmit: !!baseline.version && !conflict && !changed,
    markConflict: () => setConflict(true),
    markApplied: (snapshot: ConfigurationSnapshot<T>) => {
      setAuthored(true)
      setBaseline(remote.version === snapshot.version ? remote : snapshot)
      setPreviousRead(remote.version === baseline.version ? { version: remote.version, readAt: remote.readAt } : null)
      setConflict(false)
    },
    accept: (compared: ConfigurationSnapshot<T>) => {
      setAuthored(true)
      setBaseline(compared)
      setConflict(false)
      setPreviousRead(null)
    },
    reset: (snapshot: ConfigurationSnapshot<T>) => {
      setBaseline(snapshot)
      setDraftValue(snapshot.value)
      setAuthored(false)
      setConflict(false)
      setPreviousRead(null)
    },
  }
}
