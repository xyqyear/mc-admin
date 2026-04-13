import React, { useState, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import { Search, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Field, FieldLabel } from '@/components/ui/field'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import type { FileSearchRequest, SearchFileItem } from '@/hooks/api/fileApi'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import FileSearchResultTree from '@/components/server/FileSearchResultTree'

const sizeUnits = [
  { value: '1', label: 'B' },
  { value: '1024', label: 'KB' },
  { value: String(1024 * 1024), label: 'MB' },
  { value: String(1024 * 1024 * 1024), label: 'GB' },
  { value: String(1024 * 1024 * 1024 * 1024), label: 'TB' },
]

interface FileDeepSearchDialogProps {
  open: boolean
  onCancel: () => void
  serverId: string
  currentPath: string
  onNavigate: (path: string, query?: string, keepRegex?: boolean) => void
}

const FileDeepSearchDialog: React.FC<FileDeepSearchDialogProps> = ({
  open,
  onCancel,
  serverId,
  currentPath,
  onNavigate
}) => {
  const [regex, setRegex] = useState('')
  const [ignoreCase, setIgnoreCase] = useState(true)
  const [searchSubfolders, setSearchSubfolders] = useState(true)
  const [minSize, setMinSize] = useState('')
  const [minSizeUnit, setMinSizeUnit] = useState('1')
  const [maxSize, setMaxSize] = useState('')
  const [maxSizeUnit, setMaxSizeUnit] = useState(String(1024 * 1024))
  const [newerThan, setNewerThan] = useState('')
  const [olderThan, setOlderThan] = useState('')
  const [searchResults, setSearchResults] = useState<SearchFileItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [searchPerformed, setSearchPerformed] = useState(false)
  const [currentRegex, setCurrentRegex] = useState('')
  const searchInputRef = useRef<HTMLInputElement>(null)

  const { useSearchFiles } = useFileMutations(serverId)
  const searchFilesMutation = useSearchFiles()

  useEffect(() => {
    if (open && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100)
    }
  }, [open])

  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const selectedKey = selectedKeys[0] as string
      const selectedItem = searchResults.find(result => result.path === selectedKey)

      if (selectedItem) {
        const isFile = selectedItem.type === 'file'

        if (isFile) {
          const filePath = selectedItem.path
          const fileName = selectedItem.name
          const lastSlashIndex = filePath.lastIndexOf('/')
          const fileDirPath = lastSlashIndex > 0 ? filePath.substring(0, lastSlashIndex) : '/'

          let absoluteDirPath: string
          if (currentPath === '/') {
            absoluteDirPath = fileDirPath
          } else if (fileDirPath === '/') {
            absoluteDirPath = currentPath
          } else {
            absoluteDirPath = currentPath + (fileDirPath.startsWith('/') ? fileDirPath : '/' + fileDirPath)
          }

          onNavigate(absoluteDirPath, fileName)
        } else {
          let absoluteFolderPath: string
          if (currentPath === '/') {
            absoluteFolderPath = selectedItem.path
          } else {
            absoluteFolderPath = currentPath + (selectedItem.path.startsWith('/') ? selectedItem.path : '/' + selectedItem.path)
          }
          onNavigate(absoluteFolderPath)
        }
      } else {
        let absoluteFolderPath: string
        if (currentPath === '/') {
          absoluteFolderPath = selectedKey
        } else {
          absoluteFolderPath = currentPath + (selectedKey.startsWith('/') ? selectedKey : '/' + selectedKey)
        }
        onNavigate(absoluteFolderPath, regex, true)
      }

      handleReset()
    }
  }

  const handleSearch = async () => {
    if (!regex.trim()) {
      toast.error('请输入搜索模式')
      return
    }

    const searchRequest: FileSearchRequest = {
      regex,
      ignore_case: ignoreCase,
      search_subfolders: searchSubfolders
    }

    if (minSize && minSizeUnit) {
      searchRequest.min_size = Number(minSize) * Number(minSizeUnit)
    }
    if (maxSize && maxSizeUnit) {
      searchRequest.max_size = Number(maxSize) * Number(maxSizeUnit)
    }

    if (newerThan) {
      searchRequest.newer_than = new Date(newerThan).toISOString()
    }
    if (olderThan) {
      searchRequest.older_than = new Date(olderThan).toISOString()
    }

    try {
      const searchResponse = await searchFilesMutation.mutateAsync({
        path: currentPath,
        searchRequest
      })

      setSearchResults(searchResponse.results)
      setTotalCount(searchResponse.total_count)
      setSearchPerformed(true)
      setCurrentRegex(regex)

      toast.success(`找到 ${searchResponse.total_count} 个匹配结果`)
    } catch {
      // mutation handles error display
    }
  }

  const handleReset = () => {
    setRegex('')
    setIgnoreCase(true)
    setSearchSubfolders(true)
    setMinSize('')
    setMinSizeUnit('1')
    setMaxSize('')
    setMaxSizeUnit(String(1024 * 1024))
    setNewerThan('')
    setOlderThan('')
    setSearchResults([])
    setTotalCount(0)
    setSearchPerformed(false)
    setCurrentRegex('')
  }

  const handleCancel = () => {
    handleReset()
    onCancel()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleCancel()}>
      <DialogContent className="sm:max-w-200">
        <DialogHeader>
          <DialogTitle>高级搜索</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {/* Search form */}
          <div className="space-y-4">
            <Field>
              <FieldLabel htmlFor="search-regex">搜索模式</FieldLabel>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="search-regex"
                  ref={searchInputRef}
                  placeholder="输入正则表达式搜索文件名..."
                  value={regex}
                  onChange={(e) => {
                    setRegex(e.target.value)
                    setCurrentRegex(e.target.value)
                  }}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="pl-8"
                />
              </div>
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={ignoreCase}
                  onCheckedChange={(checked) => setIgnoreCase(checked === true)}
                  id="ignore-case"
                />
                <Label htmlFor="ignore-case" className="cursor-pointer">忽略大小写</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={searchSubfolders}
                  onCheckedChange={(checked) => setSearchSubfolders(checked === true)}
                  id="search-subfolders"
                />
                <Label htmlFor="search-subfolders" className="cursor-pointer">搜索子文件夹</Label>
              </div>
            </div>

            {/* File size filters */}
            <div className="grid grid-cols-2 gap-4">
              <Field>
                <FieldLabel htmlFor="search-min-size">最小文件大小</FieldLabel>
                <div className="flex gap-2">
                  <Input
                    id="search-min-size"
                    type="number"
                    min={0}
                    placeholder="最小大小"
                    value={minSize}
                    onChange={(e) => setMinSize(e.target.value)}
                    className="flex-1"
                  />
                  <Select
                    value={minSizeUnit}
                    onValueChange={(v) => v && setMinSizeUnit(v)}
                    itemToStringLabel={(v) => sizeUnits.find(u => u.value === v)?.label ?? v}
                  >
                    <SelectTrigger className="w-20">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {sizeUnits.map(unit => (
                        <SelectItem key={unit.value} value={unit.value}>
                          {unit.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </Field>

              <Field>
                <FieldLabel htmlFor="search-max-size">最大文件大小</FieldLabel>
                <div className="flex gap-2">
                  <Input
                    id="search-max-size"
                    type="number"
                    min={0}
                    placeholder="最大大小"
                    value={maxSize}
                    onChange={(e) => setMaxSize(e.target.value)}
                    className="flex-1"
                  />
                  <Select
                    value={maxSizeUnit}
                    onValueChange={(v) => v && setMaxSizeUnit(v)}
                    itemToStringLabel={(v) => sizeUnits.find(u => u.value === v)?.label ?? v}
                  >
                    <SelectTrigger className="w-20">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {sizeUnits.map(unit => (
                        <SelectItem key={unit.value} value={unit.value}>
                          {unit.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </Field>
            </div>

            {/* Date range filters */}
            <div className="grid grid-cols-2 gap-4">
              <Field>
                <FieldLabel htmlFor="search-newer-than">修改时间（从）</FieldLabel>
                <Input
                  id="search-newer-than"
                  type="datetime-local"
                  value={newerThan}
                  onChange={(e) => setNewerThan(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="search-older-than">修改时间（到）</FieldLabel>
                <Input
                  id="search-older-than"
                  type="datetime-local"
                  value={olderThan}
                  onChange={(e) => setOlderThan(e.target.value)}
                />
              </Field>
            </div>

            {/* Action buttons */}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={handleReset}>重置</Button>
              <Button
                onClick={handleSearch}
                disabled={searchFilesMutation.isPending}
              >
                {searchFilesMutation.isPending
                  ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  : <Search className="mr-2 h-4 w-4" />
                }
                搜索
              </Button>
            </div>
          </div>

          {/* Search results */}
          {searchPerformed && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">搜索结果 ({totalCount} 个文件)</CardTitle>
              </CardHeader>
              <CardContent>
                {searchFilesMutation.isPending ? (
                  <div className="flex justify-center py-8">
                    <Spinner className="size-8" />
                  </div>
                ) : searchResults.length > 0 ? (
                  <FileSearchResultTree
                    searchResults={searchResults}
                    currentRegex={currentRegex}
                    onSelect={handleTreeSelect}
                  />
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    没有找到匹配的文件
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default FileDeepSearchDialog
