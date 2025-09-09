import React from 'react'
import { Breadcrumb } from 'antd'
import { HomeOutlined } from '@ant-design/icons'

interface FileBreadcrumbProps {
  currentPath: string
  onNavigateToPath: (path: string) => void
}

const FileBreadcrumb: React.FC<FileBreadcrumbProps> = ({
  currentPath,
  onNavigateToPath
}) => {
  const pathSegments = currentPath.split('/').filter(Boolean)

  return (
    <Breadcrumb
      items={[
        {
          title: (
            <>
              <HomeOutlined />
              <span
                className="cursor-pointer ml-1"
                onClick={() => onNavigateToPath('/')}
              >
                根目录
              </span>
            </>
          )
        },
        ...pathSegments.map((segment, index) => ({
          title: (
            <span
              className="cursor-pointer"
              onClick={() => onNavigateToPath('/' + pathSegments.slice(0, index + 1).join('/'))}
            >
              {segment}
            </span>
          )
        }))
      ]}
    />
  )
}

export default FileBreadcrumb