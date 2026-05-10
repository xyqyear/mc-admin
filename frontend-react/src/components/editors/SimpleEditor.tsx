import React from 'react'
import Editor from '@monaco-editor/react'
import { useMonacoTheme } from '@/components/theme-provider'

export interface SimpleEditorProps {
  value?: string
  onChange?: (value: string | undefined) => void
  onMount?: (editor: any) => void
  height?: string | number
  language?: string
  readOnly?: boolean
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
  className,
  options = {}
}) => {
  const theme = useMonacoTheme()
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
