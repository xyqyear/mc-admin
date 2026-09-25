import { useState } from 'react'

export function useEditorDraft<T>(key: string | null, remote: T | undefined) {
  const [session, setSession] = useState({ key, remote, draft: remote })

  if (session.key !== key) {
    setSession({ key, remote, draft: remote })
  } else if (remote !== undefined && session.remote !== remote) {
    const pristine = session.draft === session.remote || JSON.stringify(session.draft) === JSON.stringify(session.remote)
    setSession({ key, remote, draft: pristine ? remote : session.draft })
  }

  return {
    draft: session.key === key ? session.draft : remote,
    ready: key !== null && (session.key === key ? session.remote !== undefined : remote !== undefined),
    setDraft: (draft: T) => setSession(current => ({ ...current, draft })),
    reset: (value: T) => setSession(current => ({ key, remote: current.key === key ? current.remote : remote, draft: value })),
  }
}
