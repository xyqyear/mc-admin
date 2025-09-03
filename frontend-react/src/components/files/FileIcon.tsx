import React from 'react'
import {
  FolderOutlined,
  FileOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileZipOutlined
} from '@ant-design/icons'
import type { FileItem } from '@/types/Server'

export interface FileIconProps {
  file: FileItem
}

const FileIcon: React.FC<FileIconProps> = ({ file }) => {
  if (file.type === 'directory') {
    return <FolderOutlined style={{ color: '#1890ff' }} />
  }
  
  const ext = file.name.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'txt':
    case 'log':
    case 'yml':
    case 'yaml':
    case 'json':
    case 'properties':
      return <FileTextOutlined style={{ color: '#52c41a' }} />
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
      return <FileImageOutlined style={{ color: '#fa8c16' }} />
    case 'pdf':
      return <FilePdfOutlined style={{ color: '#f5222d' }} />
    case 'zip':
    case 'jar':
      return <FileZipOutlined style={{ color: '#722ed1' }} />
    case 'db':
    case 'sqlite':
      return <DatabaseOutlined style={{ color: '#13c2c2' }} />
    default:
      return <FileOutlined />
  }
}

export default FileIcon