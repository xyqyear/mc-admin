import React from 'react'
import type { MatchResult } from '@/utils/fileSearchUtils'

interface HighlightedFileNameProps {
  name: string
  matchResult?: MatchResult
  className?: string
  onClick?: () => void
}

const HighlightedFileName: React.FC<HighlightedFileNameProps> = ({
  name,
  matchResult,
  className = '',
  onClick
}) => {
  // If there's no match result or highlighted text, just render the plain name
  if (!matchResult?.highlightedText) {
    return (
      <span className={className} onClick={onClick}>
        {name}
      </span>
    )
  }

  // Render highlighted text with dangerouslySetInnerHTML
  return (
    <span
      className={className}
      onClick={onClick}
      dangerouslySetInnerHTML={{ __html: matchResult.highlightedText }}
    />
  )
}

export default HighlightedFileName