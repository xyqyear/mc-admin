import React, { useRef, useEffect, useState } from 'react'
import Editor from '@monaco-editor/react'
import { configureMonacoYaml } from 'monaco-yaml'
import { type IDisposable } from 'monaco-editor'

export interface ComposeYamlEditorProps {
  value?: string
  onChange?: (value: string | undefined) => void
  onMount?: (editor: any) => void
  height?: string | number
  readOnly?: boolean
  theme?: 'vs-light' | 'vs-dark'
  className?: string
  path?: string
  autoHeight?: boolean
  minHeight?: number
}

const ComposeYamlEditor: React.FC<ComposeYamlEditorProps> = ({
  value,
  onChange,
  onMount,
  height = '500px',
  readOnly = false,
  theme = 'vs-light',
  className,
  path = 'docker-compose.yml',
  autoHeight = false,
  minHeight = 300
}) => {
  const editorRef = useRef<any>(null)
  const yamlDisposableRef = useRef<IDisposable | null>(null)
  const [editorHeight, setEditorHeight] = useState<number>(minHeight)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (yamlDisposableRef.current) {
        yamlDisposableRef.current.dispose()
        yamlDisposableRef.current = null
        console.log('Disposed monaco-yaml resources')
      }
    }
  }, [])

  const handleEditorMount = (editor: any, monaco: any) => {
    editorRef.current = editor

    try {
      yamlDisposableRef.current = configureMonacoYaml(monaco, {
        enableSchemaRequest: true,
        hover: true,
        completion: true,
        validate: true,
        format: true,
        schemas: [
          {
            uri: window.location.origin + '/static/mc-server-compose-schema.json',
            fileMatch: ['*docker-compose*.yml', '*docker-compose*.yaml', '*compose*.yml', '*compose*.yaml', '*.yml', '*.yaml']
          }
        ]
      })
      console.log('Monaco YAML configured successfully')
    } catch (error) {
      console.error('Failed to configure monaco-yaml:', error)
    }

    // Auto-height: listen to content size changes
    if (autoHeight) {
      const updateHeight = () => {
        const contentHeight = editor.getContentHeight()
        setEditorHeight(Math.max(contentHeight, minHeight))
      }
      updateHeight()
      editor.onDidContentSizeChange(updateHeight)
    }

    if (onMount) {
      onMount(editor)
    }
  }

  return (
    <div className={className}>
      <Editor
        height={autoHeight ? editorHeight : height}
        defaultLanguage="yaml"
        value={value}
        onChange={onChange}
        onMount={handleEditorMount}
        theme={theme}
        path={path}
        options={{
          fontSize: 13,
          fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
          lineNumbers: 'on',
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          wordWrap: 'on',
          renderLineHighlight: 'all',
          quickSuggestions: true,
          formatOnPaste: true,
          formatOnType: true,
          readOnly,
          suggestOnTriggerCharacters: true,
          acceptSuggestionOnEnter: 'on',
          acceptSuggestionOnCommitCharacter: true,
          snippetSuggestions: 'top',
          folding: true,
          foldingStrategy: 'indentation',
          showFoldingControls: 'always',
          bracketPairColorization: {
            enabled: true
          },
          guides: {
            indentation: true,
            bracketPairs: true
          },
          scrollbar: {
            alwaysConsumeMouseWheel: !autoHeight
          },
        }}
      />
    </div>
  )
}

export default ComposeYamlEditor
