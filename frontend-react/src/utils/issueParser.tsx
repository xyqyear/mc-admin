import React from 'react'
import { Tag } from 'antd'
import { getGithubIssueUrl } from '@/config/versionConfig'

/**
 * 解析文本中的 GitHub issue 引用（#123 格式）
 * 将 issue 引用转换为可点击的 Tag 组件
 *
 * @param text 要解析的文本
 * @returns React 节点数组，包含文本和 issue 标签
 */
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
      <Tag
        key={`issue-${issueId}-${matchIndex}`}
        color="blue"
        className="cursor-pointer hover:opacity-80 transition-opacity"
        onClick={(e) => {
          e.stopPropagation()
          window.open(getGithubIssueUrl(issueId), '_blank', 'noopener,noreferrer')
        }}
      >
        {fullMatch}
      </Tag>
    )

    lastIndex = matchIndex + fullMatch.length
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex))
  }

  return parts.length > 0 ? parts : [text]
}
