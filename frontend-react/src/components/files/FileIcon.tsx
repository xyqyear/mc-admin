import React from 'react'
import {
  Folder,
  FileText,
  FileCode,
  Database,
  FileImage,
  FileVideo,
  FileAudio,
  FileSpreadsheet,
  FileArchive,
  Settings,
  FileKey,
  Container,
  FlaskConical,
  FileQuestion,
  FileSearch,
} from 'lucide-react'
import type { FileItem } from '@/types/Server'

export interface FileIconProps {
  file: FileItem
}

const FileIcon: React.FC<FileIconProps> = ({ file }) => {
  if (file.type === 'directory') {
    return <Folder className="h-4 w-4 text-blue-500" />
  }

  const ext = file.name.split('.').pop()?.toLowerCase()
  const fileName = file.name.toLowerCase()

  switch (ext) {
    case 'txt':
    case 'log':
    case 'properties':
    case 'toml':
    case 'ini':
    case 'conf':
    case 'yml':
    case 'yaml':
    case 'json':
      return <FileText className="h-4 w-4 text-green-600" />

    case 'md':
    case 'markdown':
      return <FileText className="h-4 w-4 text-cyan-600" />

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
      return <FileCode className="h-4 w-4 text-purple-600" />

    case 'html':
    case 'htm':
    case 'xhtml':
      return <FileCode className="h-4 w-4 text-orange-600" />

    case 'css':
    case 'scss':
    case 'sass':
    case 'less':
    case 'styl':
      return <FileCode className="h-4 w-4 text-blue-500" />

    case 'sql':
    case 'mysql':
    case 'psql':
      return <Database className="h-4 w-4 text-green-600" />

    case 'db':
    case 'sqlite':
    case 'sqlite3':
    case 'mdb':
    case 'accdb':
      return <Database className="h-4 w-4 text-cyan-600" />

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
      return <FileImage className="h-4 w-4 text-orange-500" />

    case 'mp4':
    case 'avi':
    case 'mkv':
    case 'mov':
    case 'wmv':
    case 'flv':
    case 'webm':
    case 'm4v':
    case '3gp':
      return <FileVideo className="h-4 w-4 text-pink-500" />

    case 'mp3':
    case 'wav':
    case 'flac':
    case 'aac':
    case 'ogg':
    case 'wma':
    case 'm4a':
    case 'opus':
      return <FileAudio className="h-4 w-4 text-orange-600" />

    case 'pdf':
      return <FileText className="h-4 w-4 text-red-600" />

    case 'doc':
    case 'docx':
    case 'rtf':
    case 'odt':
      return <FileText className="h-4 w-4 text-blue-500" />

    case 'xls':
    case 'xlsx':
    case 'csv':
    case 'ods':
      return <FileSpreadsheet className="h-4 w-4 text-green-600" />

    case 'ppt':
    case 'pptx':
    case 'odp':
      return <FileText className="h-4 w-4 text-orange-600" />

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
      return <FileArchive className="h-4 w-4 text-purple-600" />

    case 'exe':
    case 'msi':
    case 'app':
    case 'deb':
    case 'rpm':
    case 'pkg':
    case 'run':
    case 'bin':
      return <FlaskConical className="h-4 w-4 text-red-600" />

    case 'env':
    case 'cfg':
    case 'config':
    case 'settings':
      return <Settings className="h-4 w-4 text-blue-600" />

    case 'pem':
    case 'crt':
    case 'cer':
    case 'key':
    case 'p12':
    case 'pfx':
    case 'jks':
    case 'keystore':
      return <FileKey className="h-4 w-4 text-orange-600" />

    case 'mcmeta':
    case 'mcfunction':
    case 'nbt':
    case 'dat':
      return <FlaskConical className="h-4 w-4 text-green-600" />

    case 'snbt':
      return <Settings className="h-4 w-4 text-purple-600" />

    default:
      if (fileName === 'dockerfile' || fileName === 'containerfile') {
        return <Container className="h-4 w-4 text-blue-600" />
      }
      if (fileName === 'makefile' || fileName === 'rakefile' || fileName === 'gemfile') {
        return <FileCode className="h-4 w-4 text-purple-600" />
      }
      if (fileName === 'readme' || fileName.includes('readme')) {
        return <FileSearch className="h-4 w-4 text-cyan-600" />
      }
      if (fileName === 'license' || fileName === 'licence' || fileName.includes('license')) {
        return <FileKey className="h-4 w-4 text-orange-600" />
      }
      if (fileName.includes('docker-compose')) {
        return <Container className="h-4 w-4 text-blue-600" />
      }

      return <FileQuestion className="h-4 w-4 text-gray-500" />
  }
}

export default FileIcon
