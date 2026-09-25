import React from 'react'
import { DiffEditor } from '@monaco-editor/react'
import { useMonacoTheme } from '@/shared/theme-provider'

export interface MonacoDiffEditorProps {
  original?: string
  modified?: string
  onMount?: (editor: any) => void
  height?: string | number
  language?: string
  className?: string
  originalTitle?: string
  modifiedTitle?: string
  readOnly?: boolean
  options?: any
}

const MonacoDiffEditor: React.FC<MonacoDiffEditorProps> = ({
  original = '',
  modified = '',
  onMount,
  height = '600px',
  language = 'yaml',
  className,
  originalTitle,
  modifiedTitle,
  options = {}
}) => {
  const theme = useMonacoTheme()

  const defaultOptions = {
    readOnly: true,
    renderSideBySide: true,
    ignoreTrimWhitespace: false,
    enableSplitViewResizing: true,
    renderIndicators: true,
    originalEditable: false,
    modifiedEditable: false,
    ...options
  }

  return (
    <div className={className}>
      {(originalTitle || modifiedTitle) && <div className="grid grid-cols-2 gap-2 border-b py-1 text-sm font-medium">
        <span>{originalTitle}</span><span>{modifiedTitle}</span>
      </div>}
      <DiffEditor
        height={height}
        language={language}
        original={original}
        modified={modified}
        onMount={onMount}
        theme={theme}
        options={defaultOptions}
      />
    </div>
  )
}

export default MonacoDiffEditor
