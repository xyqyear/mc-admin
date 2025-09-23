import React from 'react'
import {
  FolderOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileZipOutlined,
  FileExcelOutlined,
  FileWordOutlined,
  FilePptOutlined,
  CodeOutlined,
  Html5Outlined,
  VideoCameraOutlined,
  SoundOutlined,
  SettingOutlined,
  FileMarkdownOutlined,
  FileSearchOutlined,
  BugOutlined,
  FileProtectOutlined,
  ConsoleSqlOutlined,
  ExperimentOutlined,
  ApiOutlined,
  FileUnknownOutlined
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
  const fileName = file.name.toLowerCase()

  switch (ext) {
    // Text and configuration files
    case 'txt':
    case 'log':
    case 'properties':
    case 'toml':
    case 'ini':
    case 'conf':
    case 'yml':
    case 'yaml':
    case 'json':
      return <FileTextOutlined style={{ color: '#52c41a' }} />

    // Markdown files
    case 'md':
    case 'markdown':
      return <FileMarkdownOutlined style={{ color: '#13c2c2' }} />

    // Programming and script files
    case 'js':
    case 'ts':
    case 'jsx':
    case 'tsx':
    case 'py':
    case 'java':
    case 'kt':
    case 'scala':
    case 'go':
    case 'rs':
    case 'c':
    case 'cpp':
    case 'h':
    case 'hpp':
    case 'cs':
    case 'php':
    case 'rb':
    case 'swift':
    case 'dart':
    case 'r':
    case 'lua':
    case 'pl':
    case 'sh':
    case 'bash':
    case 'zsh':
    case 'fish':
    case 'ps1':
    case 'bat':
    case 'cmd':
      return <CodeOutlined style={{ color: '#722ed1' }} />

    // Web files
    case 'html':
    case 'htm':
    case 'xhtml':
      return <Html5Outlined style={{ color: '#fa541c' }} />

    case 'css':
    case 'scss':
    case 'sass':
    case 'less':
    case 'styl':
      return <BugOutlined style={{ color: '#1890ff' }} />

    // Data and database files
    case 'sql':
    case 'mysql':
    case 'psql':
      return <ConsoleSqlOutlined style={{ color: '#52c41a' }} />

    case 'db':
    case 'sqlite':
    case 'sqlite3':
    case 'mdb':
    case 'accdb':
      return <DatabaseOutlined style={{ color: '#13c2c2' }} />

    // Images
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'bmp':
    case 'webp':
    case 'svg':
    case 'ico':
    case 'tiff':
    case 'tif':
      return <FileImageOutlined style={{ color: '#fa8c16' }} />

    // Videos
    case 'mp4':
    case 'avi':
    case 'mkv':
    case 'mov':
    case 'wmv':
    case 'flv':
    case 'webm':
    case 'm4v':
    case '3gp':
      return <VideoCameraOutlined style={{ color: '#eb2f96' }} />

    // Audio files
    case 'mp3':
    case 'wav':
    case 'flac':
    case 'aac':
    case 'ogg':
    case 'wma':
    case 'm4a':
    case 'opus':
      return <SoundOutlined style={{ color: '#fa541c' }} />

    // Documents
    case 'pdf':
      return <FilePdfOutlined style={{ color: '#f5222d' }} />

    case 'doc':
    case 'docx':
    case 'rtf':
    case 'odt':
      return <FileWordOutlined style={{ color: '#1890ff' }} />

    case 'xls':
    case 'xlsx':
    case 'csv':
    case 'ods':
      return <FileExcelOutlined style={{ color: '#52c41a' }} />

    case 'ppt':
    case 'pptx':
    case 'odp':
      return <FilePptOutlined style={{ color: '#fa541c' }} />

    // Archives and packages
    case 'zip':
    case '7z':
    case 'rar':
    case 'tar':
    case 'gz':
    case 'bz2':
    case 'xz':
    case 'jar':
    case 'war':
    case 'ear':
    case 'dmg':
    case 'iso':
      return <FileZipOutlined style={{ color: '#722ed1' }} />

    // Executables and binaries
    case 'exe':
    case 'msi':
    case 'app':
    case 'deb':
    case 'rpm':
    case 'pkg':
    case 'run':
    case 'bin':
      return <ExperimentOutlined style={{ color: '#f5222d' }} />

    // Configuration and system files
    case 'env':
    case 'cfg':
    case 'config':
    case 'settings':
      return <SettingOutlined style={{ color: '#1677ff' }} />

    // Certificates and security files
    case 'pem':
    case 'crt':
    case 'cer':
    case 'key':
    case 'p12':
    case 'pfx':
    case 'jks':
    case 'keystore':
      return <FileProtectOutlined style={{ color: '#fa541c' }} />

    // Special Minecraft-related files
    case 'mcmeta':
    case 'mcfunction':
    case 'nbt':
    case 'dat':
      return <ExperimentOutlined style={{ color: '#52c41a' }} />

    default:
      // Check for specific filenames
      if (fileName === 'dockerfile' || fileName === 'containerfile') {
        return <ApiOutlined style={{ color: '#1677ff' }} />
      }
      if (fileName === 'makefile' || fileName === 'rakefile' || fileName === 'gemfile') {
        return <CodeOutlined style={{ color: '#722ed1' }} />
      }
      if (fileName === 'readme' || fileName.includes('readme')) {
        return <FileSearchOutlined style={{ color: '#13c2c2' }} />
      }
      if (fileName === 'license' || fileName === 'licence' || fileName.includes('license')) {
        return <FileProtectOutlined style={{ color: '#fa541c' }} />
      }
      if (fileName.includes('docker-compose')) {
        return <ApiOutlined style={{ color: '#1677ff' }} />
      }

      return <FileUnknownOutlined style={{ color: '#8c8c8c' }} />
  }
}

export default FileIcon