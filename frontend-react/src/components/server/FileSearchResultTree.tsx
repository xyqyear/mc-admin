import React, { useState, useMemo, useEffect } from 'react'
import { ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import FileIcon from '@/components/files/FileIcon'
import HighlightedFileName from '@/components/server/HighlightedFileName'
import type { FileItem } from '@/types/Server'
import type { SearchFileItem } from '@/hooks/api/fileApi'
import { matchRegex } from '@/utils/fileSearchUtils'

interface TreeNode {
  key: string
  name: string
  isLeaf: boolean
  size?: number
  matchResult?: ReturnType<typeof matchRegex>
  children?: TreeNode[]
}

interface FileSearchResultTreeProps {
  searchResults: SearchFileItem[]
  currentRegex: string
  onSelect: (selectedKeys: React.Key[]) => void
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const searchResultToFileItem = (result: SearchFileItem): FileItem => ({
  name: result.name,
  path: result.path,
  type: result.type,
  size: result.size,
  modified_at: new Date(result.modified_at).getTime() / 1000
})

function buildTreeData(results: SearchFileItem[], currentRegex: string): TreeNode[] {
  const nodeMap: Record<string, TreeNode> = {}
  const rootNodes: TreeNode[] = []

  results.forEach((result) => {
    const pathParts = result.path.split('/').filter(part => part)
    let currentPath = ''

    pathParts.forEach((part: string, partIndex: number) => {
      const parentPath = currentPath
      currentPath += (currentPath ? '/' : '') + part
      const isLastPart = partIndex === pathParts.length - 1
      const nodeKey = '/' + currentPath

      if (!nodeMap[nodeKey]) {
        const matchResult = currentRegex ? matchRegex(part, currentRegex) : undefined

        const node: TreeNode = {
          key: nodeKey,
          name: part,
          isLeaf: isLastPart,
          size: isLastPart && result.type === 'file' ? result.size : undefined,
          matchResult,
          children: isLastPart ? undefined : [],
        }
        nodeMap[nodeKey] = node

        const parentKey = parentPath ? '/' + parentPath : ''
        if (parentPath && nodeMap[parentKey]) {
          nodeMap[parentKey].children = nodeMap[parentKey].children || []
          nodeMap[parentKey].children!.push(node)
        } else if (!parentPath) {
          rootNodes.push(node)
        }
      }
    })
  })

  return rootNodes
}

function getAllKeys(nodes: TreeNode[]): string[] {
  const keys: string[] = []
  const traverse = (list: TreeNode[]) => {
    list.forEach(node => {
      keys.push(node.key)
      if (node.children) traverse(node.children)
    })
  }
  traverse(nodes)
  return keys
}

const TreeNodeRow: React.FC<{
  node: TreeNode
  level: number
  expandedKeys: Set<string>
  searchResults: SearchFileItem[]
  onToggle: (key: string) => void
  onSelect: (key: string) => void
}> = ({ node, level, expandedKeys, searchResults, onToggle, onSelect }) => {
  const isExpanded = expandedKeys.has(node.key)
  const hasChildren = !!node.children?.length

  const nodeItem: SearchFileItem = useMemo(() => {
    if (node.isLeaf) {
      const found = searchResults.find(r => r.path === node.key)
      if (found) return found
    }
    return {
      name: node.name,
      path: node.key,
      type: hasChildren ? 'directory' as const : 'file' as const,
      size: 0,
      modified_at: new Date().toISOString(),
    }
  }, [node, hasChildren, searchResults])

  return (
    <>
      <div
        className="flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 rounded cursor-pointer"
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => {
          if (hasChildren) onToggle(node.key)
          onSelect(node.key)
        }}
      >
        {hasChildren ? (
          <span className="shrink-0">
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </span>
        ) : (
          <span className="w-3.5" />
        )}
        <span className="shrink-0">
          <FileIcon file={searchResultToFileItem(nodeItem)} />
        </span>
        <HighlightedFileName name={node.name} matchResult={node.matchResult} />
        {node.isLeaf && node.size != null && (
          <span className="text-xs text-muted-foreground ml-1">
            ({formatFileSize(node.size)})
          </span>
        )}
      </div>
      {isExpanded && node.children?.map(child => (
        <TreeNodeRow
          key={child.key}
          node={child}
          level={level + 1}
          expandedKeys={expandedKeys}
          searchResults={searchResults}
          onToggle={onToggle}
          onSelect={onSelect}
        />
      ))}
    </>
  )
}

const FileSearchResultTree: React.FC<FileSearchResultTreeProps> = ({
  searchResults,
  currentRegex,
  onSelect
}) => {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const treeData = useMemo(() => buildTreeData(searchResults, currentRegex), [searchResults, currentRegex])

  useEffect(() => {
    if (searchResults.length > 0) {
      setExpandedKeys(new Set(getAllKeys(treeData)))
    } else {
      setExpandedKeys(new Set())
    }
  }, [searchResults, treeData])

  const handleToggle = (key: string) => {
    setExpandedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleSelect = (key: string) => {
    onSelect([key])
  }

  const handleExpandAll = () => {
    setExpandedKeys(new Set(getAllKeys(treeData)))
  }

  const handleCollapseAll = () => {
    setExpandedKeys(new Set())
  }

  return (
    <div>
      {treeData.length > 0 && (
        <div className="mb-3 flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={handleExpandAll}>
            <Maximize2 className="mr-1 h-3.5 w-3.5" />
            展开所有
          </Button>
          <Button variant="ghost" size="sm" onClick={handleCollapseAll}>
            <Minimize2 className="mr-1 h-3.5 w-3.5" />
            收起所有
          </Button>
        </div>
      )}

      <div className="max-h-96 overflow-y-auto">
        {treeData.map(node => (
          <TreeNodeRow
            key={node.key}
            node={node}
            level={0}
            expandedKeys={expandedKeys}
            searchResults={searchResults}
            onToggle={handleToggle}
            onSelect={handleSelect}
          />
        ))}
      </div>
    </div>
  )
}

export default FileSearchResultTree
