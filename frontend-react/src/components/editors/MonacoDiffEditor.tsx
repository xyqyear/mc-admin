import React from 'react'
import { DiffEditor } from '@monaco-editor/react'

export interface MonacoDiffEditorProps {
  original?: string
  modified?: string
  onMount?: (editor: any) => void
  height?: string | number
  language?: string
  theme?: 'vs-light' | 'vs-dark'
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
  theme = 'vs-light',
  className,
  options = {}
}) => {
  const handleMount = (editor: any) => {
    console.log('Diff editor mounted:', {
      original: original.substring(0, 50) + '...',
      modified: modified.substring(0, 50) + '...',
      areDifferent: original !== modified
    })

    if (onMount) {
      onMount(editor)
    }
  }

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
      <DiffEditor
        height={height}
        language={language}
        original={original}
        modified={modified}
        onMount={handleMount}
        theme={theme}
        options={defaultOptions}
      />
    </div>
  )
}

export default MonacoDiffEditor
