import React from 'react'
import { Home } from 'lucide-react'
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

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
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          {pathSegments.length === 0 ? (
            <BreadcrumbPage className="inline-flex items-center gap-1">
              <Home className="h-3.5 w-3.5" />
              根目录
            </BreadcrumbPage>
          ) : (
            <BreadcrumbLink
              className="inline-flex items-center gap-1 cursor-pointer"
              onClick={() => onNavigateToPath('/')}
            >
              <Home className="h-3.5 w-3.5" />
              根目录
            </BreadcrumbLink>
          )}
        </BreadcrumbItem>
        {pathSegments.map((segment, index) => {
          const isLast = index === pathSegments.length - 1
          const path = '/' + pathSegments.slice(0, index + 1).join('/')
          return (
            <React.Fragment key={path}>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{segment}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink
                    className="cursor-pointer"
                    onClick={() => onNavigateToPath(path)}
                  >
                    {segment}
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

export default FileBreadcrumb
