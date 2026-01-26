import React from 'react'
import type { MatchResult } from '@/utils/fileSearchUtils'

interface HighlightedFileNameProps {
  name: string
  matchResult?: MatchResult
  className?: string
  onClick?: () => void
}

const HighlightedFileName = React.forwardRef<HTMLSpanElement, HighlightedFileNameProps>(
  ({ name, matchResult, className = '', onClick }, ref) => {
    if (!matchResult?.highlightedText) {
      return (
        <span ref={ref} className={className} onClick={onClick}>
          {name}
        </span>
      )
    }

    return (
      <span
        ref={ref}
        className={className}
        onClick={onClick}
        dangerouslySetInnerHTML={{ __html: matchResult.highlightedText }}
      />
    )
  }
)

HighlightedFileName.displayName = 'HighlightedFileName'

export default HighlightedFileName