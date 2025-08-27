import React from 'react'
import Editor from '@monaco-editor/react'

export interface SimpleEditorProps {
  value?: string
  onChange?: (value: string | undefined) => void
  onMount?: (editor: any) => void
  height?: string | number
  language?: string
  readOnly?: boolean
  theme?: 'vs-light' | 'vs-dark'
  className?: string
  options?: any
}

const SimpleEditor: React.FC<SimpleEditorProps> = ({
  value,
  onChange,
  onMount,
  height = '500px',
  language = 'text',
  readOnly = false,
  theme = 'vs-light',
  className,
  options = {}
}) => {
  const defaultOptions = {
    fontSize: 13,
    fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
    lineNumbers: 'on',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 2,
    wordWrap: 'on',
    renderLineHighlight: 'all',
    readOnly,
    formatOnPaste: true,
    formatOnType: language === 'yaml' || language === 'json',
    quickSuggestions: language === 'yaml' || language === 'json' || language === 'javascript' || language === 'typescript',
    folding: true,
    foldingStrategy: 'indentation',
    showFoldingControls: 'mouseover',
    bracketPairColorization: {
      enabled: true
    },
    guides: {
      indentation: true,
      bracketPairs: true
    },
    // Merge with user-provided options
    ...options
  }

  return (
    <div className={className}>
      <Editor
        height={height}
        defaultLanguage={language}
        value={value}
        onChange={onChange}
        onMount={onMount}
        theme={theme}
        options={defaultOptions}
      />
    </div>
  )
}

export default SimpleEditor
