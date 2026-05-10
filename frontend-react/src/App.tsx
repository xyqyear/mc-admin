import React, { ErrorInfo, Suspense } from 'react'
import { ErrorBoundary } from 'react-error-boundary'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { ErrorFallback } from '@/components/layout/ErrorFallback'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { MainLayout } from '@/components/layout/MainLayout'
import VersionUpdateDialog from '@/components/VersionUpdateDialog'
import { useVersionCheck } from '@/hooks/useVersionCheck'
import { useTokenStore } from '@/stores/useTokenStore'
import { toast } from 'sonner'

const Login = React.lazy(() => import('@/pages/Login'))
const Home = React.lazy(() => import('@/pages/Home'))
const Overview = React.lazy(() => import('@/pages/Overview'))
const Snapshots = React.lazy(() => import('@/pages/Snapshots'))
const ArchiveManagement = React.lazy(() => import('@/pages/ArchiveManagement'))
const DynamicConfig = React.lazy(() => import('@/pages/DynamicConfig'))
const CronManagement = React.lazy(() => import('@/pages/CronManagement'))
const DnsManagement = React.lazy(() => import('@/pages/DnsManagement'))
const PlayerManagement = React.lazy(() => import('@/pages/PlayerManagement'))
const ServerNew = React.lazy(() => import('@/pages/server/ServerNew'))
const ServerDetail = React.lazy(() => import('@/pages/server/servers/ServerDetail'))
const ServerFiles = React.lazy(() => import('@/pages/server/servers/ServerFiles'))
const ServerCompose = React.lazy(() => import('@/pages/server/servers/ServerCompose'))
const ServerConsole = React.lazy(() => import('@/pages/server/servers/ServerConsole'))
const ServerWorldRestore = React.lazy(() => import('@/pages/server/servers/ServerWorldRestore'))
const UserManagement = React.lazy(() => import('@/pages/admin/UserManagement'))
const TemplateList = React.lazy(() => import('@/pages/templates/TemplateList'))
const TemplateEdit = React.lazy(() => import('@/pages/templates/TemplateEdit'))
const DefaultVariables = React.lazy(() => import('@/pages/templates/DefaultVariables'))



function ProtectedRoutes() {
  const token = useTokenStore((state) => state.token)

  if (!token) {
    return <Navigate to="/login" replace />
  }

  return (
    <MainLayout>
      <Suspense fallback={<LoadingSpinner />}>
        <Outlet />
      </Suspense>
    </MainLayout>
  )
}

function AuthRoutes() {
  const token = useTokenStore((state) => state.token)

  if (token) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

function App() {
  const { shouldShowDialog, fromVersion, toVersion, handleClose, handleRemindLater } = useVersionCheck()

  const handleError = (error: unknown, errorInfo: ErrorInfo) => {
    console.error('Application error:', error, errorInfo)
    toast.error('Application Error', {
      description: 'An unexpected error occurred. Please refresh the page.',
      duration: Infinity,
    })
  }

  return (
    <ErrorBoundary FallbackComponent={ErrorFallback} onError={handleError}>
      <Routes>
        <Route element={<AuthRoutes />}>
          <Route path="/login" element={
            <Suspense fallback={<LoadingSpinner fullscreen />}>
              <Login />
            </Suspense>
          } />
        </Route>

        <Route element={<ProtectedRoutes />}>
          <Route path="/" element={<Home />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/snapshots" element={<Snapshots />} />
          <Route path="/archives" element={<ArchiveManagement />} />
          <Route path="/config" element={<DynamicConfig />} />
          <Route path="/cron" element={<CronManagement />} />
          <Route path="/dns" element={<DnsManagement />} />
          <Route path="/players" element={<PlayerManagement />} />
          <Route path="/server">
            <Route path="new" element={<ServerNew />} />
            <Route path=":id" element={<ServerDetail />} />
            <Route path=":id/files" element={<ServerFiles />} />
            <Route path=":id/compose" element={<ServerCompose />} />
            <Route path=":id/console" element={<ServerConsole />} />
            <Route path=":id/world-restore" element={<ServerWorldRestore />} />
          </Route>
          <Route path="/admin">
            <Route path="users" element={<UserManagement />} />
          </Route>
          <Route path="/templates">
            <Route index element={<TemplateList />} />
            <Route path="new" element={<TemplateEdit />} />
            <Route path="default-variables" element={<DefaultVariables />} />
            <Route path=":id/edit" element={<TemplateEdit />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <VersionUpdateDialog
        open={shouldShowDialog}
        onClose={handleClose}
        onRemindLater={handleRemindLater}
        fromVersion={fromVersion}
        toVersion={toVersion}
      />
    </ErrorBoundary>
  )
}

export default App
