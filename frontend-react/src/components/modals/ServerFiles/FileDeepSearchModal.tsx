import React, { useState } from 'react'
import {
  Modal,
  Form,
  Input,
  Checkbox,
  Button,
  InputNumber,
  Select,
  DatePicker,
  Card,
  message,
  Spin,
  Empty,
  Flex
} from 'antd'
import {
  SearchOutlined
} from '@ant-design/icons'
import type { FileSearchRequest, SearchFileItem } from '@/hooks/api/fileApi'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import FileSearchResultTree from '@/components/server/FileSearchResultTree'

const { RangePicker } = DatePicker
const { Option } = Select

// 文件大小单位选项
const sizeUnits = [
  { value: 1, label: 'B' },
  { value: 1024, label: 'KB' },
  { value: 1024 * 1024, label: 'MB' },
  { value: 1024 * 1024 * 1024, label: 'GB' },
  { value: 1024 * 1024 * 1024 * 1024, label: 'TB' }
]

interface FileDeepSearchModalProps {
  open: boolean
  onCancel: () => void
  serverId: string
  currentPath: string
  onNavigate: (path: string, query?: string, keepRegex?: boolean) => void
}

const FileDeepSearchModal: React.FC<FileDeepSearchModalProps> = ({
  open,
  onCancel,
  serverId,
  currentPath,
  onNavigate
}) => {
  const [form] = Form.useForm()
  const [searchResults, setSearchResults] = useState<SearchFileItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [searchPerformed, setSearchPerformed] = useState(false)
  const [currentRegex, setCurrentRegex] = useState<string>('')
  const searchInputRef = React.useRef<any>(null)

  // 使用文件mutations
  const { useSearchFiles } = useFileMutations(serverId)
  const searchFilesMutation = useSearchFiles()

  // Auto-focus to search input when modal opens
  React.useEffect(() => {
    if (open && searchInputRef.current) {
      // Use setTimeout to ensure the modal is fully rendered before focusing
      setTimeout(() => {
        searchInputRef.current?.focus()
      }, 100)
    }
  }, [open])

  // Handle form values change to update regex for highlighting
  const handleValuesChange = (changedValues: any) => {
    if ('regex' in changedValues) {
      setCurrentRegex(changedValues.regex || '')
    }
  }


  // Handle tree node selection
  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const selectedKey = selectedKeys[0] as string

      // Find the corresponding item from search results
      const selectedItem = searchResults.find(result => result.path === selectedKey)

      if (selectedItem) {
        const isFile = selectedItem.type === 'file'

        if (isFile) {
          // 对于文件：导航到文件所在的文件夹，并设置搜索查询为文件名
          const filePath = selectedItem.path // 比如 /saves/level.dat
          const fileName = selectedItem.name // 比如 level.dat

          // 计算文件所在的父文件夹路径（相对于搜索起点）
          const lastSlashIndex = filePath.lastIndexOf('/')
          const fileDirPath = lastSlashIndex > 0 ? filePath.substring(0, lastSlashIndex) : '/'

          // 将相对路径转换为基于currentPath的绝对路径
          let absoluteDirPath: string
          if (currentPath === '/') {
            absoluteDirPath = fileDirPath
          } else if (fileDirPath === '/') {
            absoluteDirPath = currentPath
          } else {
            // 确保路径拼接时有正确的斜杠
            absoluteDirPath = currentPath + (fileDirPath.startsWith('/') ? fileDirPath : '/' + fileDirPath)
          }

          // 导航到文件的父文件夹，搜索查询设置为文件名
          onNavigate(absoluteDirPath, fileName)
        } else {
          // 对于文件夹：导航到该文件夹，并去除搜索查询
          // 将相对路径转换为基于currentPath的绝对路径
          let absoluteFolderPath: string
          if (currentPath === '/') {
            absoluteFolderPath = selectedItem.path
          } else {
            // 确保路径拼接时有正确的斜杠
            absoluteFolderPath = currentPath + (selectedItem.path.startsWith('/') ? selectedItem.path : '/' + selectedItem.path)
          }
          onNavigate(absoluteFolderPath)
        }
      } else {
        // This is a directory node that was created for the tree structure (intermediate directories)
        // Navigate to the directory path directly
        const regex = form.getFieldValue('regex')
        // 将相对路径转换为基于currentPath的绝对路径
        let absoluteFolderPath: string
        if (currentPath === '/') {
          absoluteFolderPath = selectedKey
        } else {
          // 确保路径拼接时有正确的斜杠
          absoluteFolderPath = currentPath + (selectedKey.startsWith('/') ? selectedKey : '/' + selectedKey)
        }
        onNavigate(absoluteFolderPath, regex, true)
      }

      // 清空所有状态
      handleReset()
    }
  }


  // 执行搜索
  const handleSearch = async () => {
    try {
      await form.validateFields()
      const values = form.getFieldsValue()

      // 构建搜索请求
      const searchRequest: FileSearchRequest = {
        regex: values.regex,
        ignore_case: values.ignore_case !== false, // 默认为true
        search_subfolders: values.search_subfolders !== false // 默认为true
      }

      // 处理文件大小限制
      if (values.minSize && values.minSizeUnit) {
        searchRequest.min_size = values.minSize * values.minSizeUnit
      }
      if (values.maxSize && values.maxSizeUnit) {
        searchRequest.max_size = values.maxSize * values.maxSizeUnit
      }

      // 处理日期范围
      if (values.dateRange && values.dateRange.length === 2) {
        const [startDate, endDate] = values.dateRange
        if (startDate) {
          searchRequest.newer_than = startDate.toISOString()
        }
        if (endDate) {
          searchRequest.older_than = endDate.toISOString()
        }
      }

      // 执行搜索
      const searchResponse = await searchFilesMutation.mutateAsync({
        path: currentPath,
        searchRequest
      })

      setSearchResults(searchResponse.results)
      setTotalCount(searchResponse.total_count)
      setSearchPerformed(true)

      message.success(`找到 ${searchResponse.total_count} 个匹配结果`)
    } catch (error: any) {
      console.error('搜索失败:', error.response?.data?.detail || error.message || 'Unknown error')
      // mutation已经处理了错误消息显示
    }
  }

  // 重置表单和结果
  const handleReset = () => {
    form.resetFields()
    setSearchResults([])
    setTotalCount(0)
    setSearchPerformed(false)
    setCurrentRegex('')
  }


  // 模态框关闭时重置表单
  const handleCancel = () => {
    handleReset()
    onCancel()
  }


  return (
    <Modal
      title="高级搜索"
      open={open}
      onCancel={handleCancel}
      width={800}
      footer={null}
    >
      <div className="space-y-4">
        {/* 搜索表单 */}
        <Form
          form={form}
          layout="vertical"
          initialValues={{ ignore_case: true, search_subfolders: true }}
          onValuesChange={handleValuesChange}
        >
          <Form.Item
            label="搜索模式"
            name="regex"
            rules={[{ required: true, message: '请输入搜索模式' }]}
          >
            <Input
              ref={searchInputRef}
              placeholder="输入正则表达式搜索文件名..."
              prefix={<SearchOutlined />}
              onPressEnter={handleSearch}
            />
          </Form.Item>

          <div className="grid grid-cols-2 gap-4">
            <Form.Item name="ignore_case" valuePropName="checked">
              <Checkbox>忽略大小写</Checkbox>
            </Form.Item>
            <Form.Item name="search_subfolders" valuePropName="checked">
              <Checkbox>搜索子文件夹</Checkbox>
            </Form.Item>
          </div>

          {/* 文件大小过滤 */}
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="最小文件大小">
              <Flex>
                <Form.Item name="minSize" noStyle>
                  <InputNumber min={0} placeholder="最小大小" style={{ flex: 1 }} />
                </Form.Item>
                <Form.Item name="minSizeUnit" noStyle initialValue={1}>
                  <Select style={{ width: 80, marginLeft: 8 }}>
                    {sizeUnits.map(unit => (
                      <Option key={unit.value} value={unit.value}>{unit.label}</Option>
                    ))}
                  </Select>
                </Form.Item>
              </Flex>
            </Form.Item>

            <Form.Item label="最大文件大小">
              <Flex>
                <Form.Item name="maxSize" noStyle>
                  <InputNumber min={0} placeholder="最大大小" style={{ flex: 1 }} />
                </Form.Item>
                <Form.Item name="maxSizeUnit" noStyle initialValue={1024 * 1024}>
                  <Select style={{ width: 80, marginLeft: 8 }}>
                    {sizeUnits.map(unit => (
                      <Option key={unit.value} value={unit.value}>{unit.label}</Option>
                    ))}
                  </Select>
                </Form.Item>
              </Flex>
            </Form.Item>
          </div>

          {/* 日期范围过滤 */}
          <Form.Item label="文件修改时间" name="dateRange">
            <RangePicker showTime placeholder={['开始时间', '结束时间']} />
          </Form.Item>

          {/* 操作按钮 */}
          <div className="flex justify-end space-x-2">
            <Button onClick={handleReset}>重置</Button>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={searchFilesMutation.isPending}
              onClick={handleSearch}
            >
              搜索
            </Button>
          </div>
        </Form>

        {/* 搜索结果 */}
        {searchPerformed && (
          <Card
            title={`搜索结果 (${totalCount} 个文件)`}
            size="small"
          >
            {searchFilesMutation.isPending ? (
              <div className="flex justify-center py-8">
                <Spin size="large" />
              </div>
            ) : searchResults.length > 0 ? (
              <FileSearchResultTree
                searchResults={searchResults}
                currentRegex={currentRegex}
                onSelect={handleTreeSelect}
              />
            ) : searchPerformed ? (
              <Empty
                description="没有找到匹配的文件"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : null}
          </Card>
        )}
      </div>
    </Modal>
  )
}

export default FileDeepSearchModal