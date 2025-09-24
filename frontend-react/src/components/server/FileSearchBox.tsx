import React, { useCallback, useRef, forwardRef, useImperativeHandle } from 'react'
import { Input, Checkbox, Tooltip, Space } from 'antd'
import { SearchOutlined, ClearOutlined, CodeOutlined } from '@ant-design/icons'

interface FileSearchBoxProps {
  searchTerm: string
  useRegex: boolean
  onSearchChange: (term: string) => void
  onRegexChange: (useRegex: boolean) => void
  onClear: () => void
  placeholder?: string
  className?: string
}

export interface FileSearchBoxRef {
  focus: () => void
}

const FileSearchBox = forwardRef<FileSearchBoxRef, FileSearchBoxProps>(({
  searchTerm,
  useRegex,
  onSearchChange,
  onRegexChange,
  onClear,
  placeholder = "搜索文件名...",
  className = ""
}, ref) => {
  const inputRef = useRef<any>(null)

  // Expose focus method through ref
  useImperativeHandle(ref, () => ({
    focus: () => {
      inputRef.current?.focus()
    }
  }))

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onSearchChange(e.target.value)
  }, [onSearchChange])

  const handleClear = useCallback(() => {
    onClear()
  }, [onClear])

  const handleRegexChange = useCallback((e: any) => {
    onRegexChange(e.target.checked)
  }, [onRegexChange])

  // Handle keyboard events
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      handleClear()
      // Keep focus on input after clearing
      inputRef.current?.focus()
    }
  }, [handleClear])

  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      <Input
        ref={inputRef}
        placeholder={placeholder}
        prefix={<SearchOutlined className="text-gray-400" />}
        suffix={
          searchTerm ? (
            <Tooltip title="清除搜索">
              <ClearOutlined
                className="text-gray-400 hover:text-gray-600 cursor-pointer"
                onClick={handleClear}
              />
            </Tooltip>
          ) : null
        }
        value={searchTerm}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        className="flex-1 min-w-0"
        allowClear={false} // We handle clear ourselves for better control
      />

      <Tooltip title="使用正则表达式搜索">
        <Checkbox
          checked={useRegex}
          onChange={handleRegexChange}
          className="whitespace-nowrap"
        >
          <Space align="center">
            <CodeOutlined />
            <span className="hidden sm:inline">正则</span>
          </Space>
        </Checkbox>
      </Tooltip>
    </div>
  )
})

FileSearchBox.displayName = 'FileSearchBox'

export default FileSearchBox