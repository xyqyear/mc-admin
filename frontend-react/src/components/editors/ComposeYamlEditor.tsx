import React, { useRef } from 'react'
import Editor from '@monaco-editor/react'
import { configureMonacoYaml } from 'monaco-yaml'

export interface ComposeYamlEditorProps {
  value?: string
  onChange?: (value: string | undefined) => void
  onMount?: (editor: any) => void
  height?: string | number
  readOnly?: boolean
  theme?: 'vs-light' | 'vs-dark'
  className?: string
  path?: string  // Add path prop for model URI
}

const ComposeYamlEditor: React.FC<ComposeYamlEditorProps> = ({
  value,
  onChange,
  onMount,
  height = '500px',
  readOnly = false,
  theme = 'vs-light',
  className,
  path = 'docker-compose.yml'  // Default to docker-compose.yml
}) => {
  const editorRef = useRef<any>(null)
  const isConfigured = useRef(false)

  const handleEditorMount = (editor: any, monaco: any) => {
    editorRef.current = editor

    // Configure YAML support only once
    if (!isConfigured.current) {
      try {
        configureMonacoYaml(monaco, {
          enableSchemaRequest: false,
          hover: true,
          completion: true,
          validate: true,
          format: true,
          schemas: [
            {
              uri: window.location.origin + '/static/compose-spec.json',
              fileMatch: ['*docker-compose*.yml', '*docker-compose*.yaml', '*compose*.yml', '*compose*.yaml', '*.yml', '*.yaml']
            }
          ]
        })
        isConfigured.current = true
        console.log('Monaco YAML configured successfully')
      } catch (error) {
        console.error('Failed to configure monaco-yaml:', error)
        // Even if YAML configuration fails, the editor should still work with basic syntax highlighting
      }
    }

    // Call user-provided onMount callback
    if (onMount) {
      onMount(editor)
    }
  }

  return (
    <div className={className}>
      <Editor
        height={height}
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
          }
        }}
      />
    </div>
  )
}

export default ComposeYamlEditor
