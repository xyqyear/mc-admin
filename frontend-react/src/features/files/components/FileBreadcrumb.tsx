import React from 'react'
import { Home } from 'lucide-react'
import { Link } from 'react-router'
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/shared/ui/breadcrumb'

interface FileBreadcrumbProps {
  currentPath: string
  getPathHref: (path: string) => string
  onNavigateToPath: (path: string) => void
}

const FileBreadcrumb: React.FC<FileBreadcrumbProps> = ({
  currentPath,
  getPathHref,
  onNavigateToPath
}) => {
  const pathSegments = currentPath.split('/').filter(Boolean)
  const handleNavigate = (event: React.MouseEvent<HTMLAnchorElement>, path: string) => {
    if (event.defaultPrevented || event.button !== 0
      || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    onNavigateToPath(path)
  }

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
              render={<Link to={getPathHref('/')} />}
              className="inline-flex items-center gap-1 cursor-pointer"
              onClick={(event) => handleNavigate(event, '/')}
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
                    render={<Link to={getPathHref(path)} />}
                    className="cursor-pointer"
                    onClick={(event) => handleNavigate(event, path)}
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
