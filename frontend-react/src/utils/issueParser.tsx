import React from 'react'
import { StatusBadge } from '@/components/common/StatusBadge'
import { getGithubIssueUrl } from '@/config/versionConfig'

export const parseIssueReferences = (text: string): React.ReactNode[] => {
  const issuePattern = /#(\d+)/g
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = issuePattern.exec(text)) !== null) {
    const fullMatch = match[0]
    const issueId = match[1]
    const matchIndex = match.index

    if (matchIndex > lastIndex) {
      parts.push(text.substring(lastIndex, matchIndex))
    }

    parts.push(
      <StatusBadge
        key={`issue-${issueId}-${matchIndex}`}
        tone="info"
        badgeStyle="soft"
        className="cursor-pointer hover:opacity-80 transition-opacity mx-0.5"
        onClick={(e) => {
          e.stopPropagation()
          window.open(getGithubIssueUrl(issueId), '_blank', 'noopener,noreferrer')
        }}
      >
        {fullMatch}
      </StatusBadge>
    )

    lastIndex = matchIndex + fullMatch.length
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex))
  }

  return parts.length > 0 ? parts : [text]
}
