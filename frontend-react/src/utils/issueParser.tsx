import React from 'react'
import { Badge } from '@/components/ui/badge'
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
      <Badge
        key={`issue-${issueId}-${matchIndex}`}
        variant="secondary"
        className="cursor-pointer bg-blue-100 text-blue-700 border-blue-200 hover:bg-blue-200 hover:opacity-90 transition-colors mx-0.5"
        onClick={(e) => {
          e.stopPropagation()
          window.open(getGithubIssueUrl(issueId), '_blank', 'noopener,noreferrer')
        }}
      >
        {fullMatch}
      </Badge>
    )

    lastIndex = matchIndex + fullMatch.length
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex))
  }

  return parts.length > 0 ? parts : [text]
}
