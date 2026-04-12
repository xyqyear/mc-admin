import React, { useCallback, useRef, forwardRef, useImperativeHandle } from 'react'
import { Search, X, Regex } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from '@/components/ui/tooltip'

interface FileSearchBoxProps {
  searchTerm: string
  useRegex: boolean
  onSearchChange: (term: string) => void
  onRegexChange: (useRegex: boolean) => void
  onClear: () => void
  onSearch?: (term: string, regex: boolean) => void
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
  onSearch,
  placeholder = "搜索文件名...",
  className = ""
}, ref) => {
  const inputRef = useRef<HTMLInputElement>(null)

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

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      onSearch?.(searchTerm, useRegex)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      handleClear()
      inputRef.current?.focus()
    }
  }, [handleClear, onSearch, searchTerm, useRegex])

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="relative flex-1 min-w-0">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          ref={inputRef}
          placeholder={placeholder}
          value={searchTerm}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          className="pl-8 pr-8"
        />
        {searchTerm && (
          <Tooltip>
            <TooltipTrigger
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              onClick={handleClear}
            >
              <X className="h-4 w-4" />
            </TooltipTrigger>
            <TooltipContent>清除搜索</TooltipContent>
          </Tooltip>
        )}
      </div>

      <Tooltip>
        <TooltipTrigger className="inline-flex items-center gap-1.5">
          <Checkbox
            checked={useRegex}
            onCheckedChange={(checked) => onRegexChange(checked === true)}
            id="regex-toggle"
          />
          <Label htmlFor="regex-toggle" className="flex items-center gap-1 cursor-pointer whitespace-nowrap text-sm">
            <Regex className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">正则</span>
          </Label>
        </TooltipTrigger>
        <TooltipContent>使用正则表达式搜索</TooltipContent>
      </Tooltip>
    </div>
  )
})

FileSearchBox.displayName = 'FileSearchBox'

export default FileSearchBox
