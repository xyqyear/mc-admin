import React, { Suspense, useEffect } from 'react'
import type { ErrorInfo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ErrorBoundary } from 'react-error-boundary'
import { Navigate, Outlet, Route, Routes, useNavigate } from 'react-router'
import { ErrorFallback } from '@/shared/layout/ErrorFallback'
import { LoadingSpinner } from '@/shared/layout/LoadingSpinner'
import { MainLayout } from '@/app/layout/MainLayout'
import VersionUpdateDialog from '@/app/version/VersionUpdateDialog'
import { useCurrentUser } from '@/features/users/queries'
import { useVersionCheck } from '@/app/version/useVersionCheck'
import { AUTH_EXPIRED_EVENT, getErrorStatus } from '@/shared/http/api'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { OperationObserver } from '@/app/operations/OperationObserver'

const Login = React.lazy(() => import('@/features/users/LoginScreen'))
const SelfCheck = React.lazy(() => import('@/features/health/SelfCheckScreen'))
const Overview = React.lazy(() => import('@/app/overview/Overview'))
const Snapshots = React.lazy(() => import('@/features/backups/SnapshotsScreen'))
const ArchiveManagement = React.lazy(() => import('@/features/archives/ArchiveManagementScreen'))
const DynamicConfig = React.lazy(() => import('@/features/settings/DynamicConfigScreen'))
const CronManagement = React.lazy(() => import('@/features/schedules/CronManagementScreen'))
const DnsManagement = React.lazy(() => import('@/features/dns/DnsManagementScreen'))
const PlayerManagement = React.lazy(() => import('@/features/players/PlayerManagementScreen'))
const ServerNew = React.lazy(() => import('@/features/servers/ServerNewScreen'))
const ServerDetail = React.lazy(() => import('@/features/servers/ServerDetailScreen'))
const ServerFiles = React.lazy(() => import('@/pages/server/servers/ServerFiles'))
const ServerCompose = React.lazy(() => import('@/pages/server/servers/ServerCompose'))
const ServerConsole = React.lazy(() => import('@/features/servers/ServerConsoleScreen'))
const ServerWorldRestore = React.lazy(() => import('@/pages/server/servers/ServerWorldRestore'))
const ServerChunkPrune = React.lazy(() => import('@/pages/server/servers/ServerChunkPrune'))
const UserManagement = React.lazy(() => import('@/features/users/UserManagementScreen'))
const TemplateList = React.lazy(() => import('@/features/templates/TemplateListScreen'))
const TemplateEdit = React.lazy(() => import('@/features/templates/TemplateEditScreen'))
const DefaultVariables = React.lazy(() => import('@/features/templates/DefaultVariablesScreen'))



function ProtectedRoutes() {
  const currentUserQuery = useCurrentUser()

  if (currentUserQuery.isLoading) {
    return <LoadingSpinner fullscreen />
  }

  const status = getErrorStatus(currentUserQuery.error)
  if (currentUserQuery.isError && status !== 401 && status !== 403 && !currentUserQuery.data) {
    return <SessionLookupError message={currentUserQuery.error.message} retry={() => { void currentUserQuery.refetch() }} />
  }

  if (!currentUserQuery.data || status === 401 || status === 403) {
    return <Navigate to="/login" replace />
  }

  return (
    <MainLayout>
      <OperationObserver key={currentUserQuery.data.id} sessionId={String(currentUserQuery.data.id)} />
      <Suspense fallback={<LoadingSpinner />}>
        <Outlet />
      </Suspense>
    </MainLayout>
  )
}

function AuthRoutes() {
  const currentUserQuery = useCurrentUser()

  if (currentUserQuery.isLoading) {
    return <LoadingSpinner fullscreen />
  }

  const status = getErrorStatus(currentUserQuery.error)
  if (currentUserQuery.isError && status !== 401 && status !== 403 && !currentUserQuery.data) {
    return <SessionLookupError message={currentUserQuery.error.message} retry={() => { void currentUserQuery.refetch() }} />
  }

  if (currentUserQuery.data && status !== 401 && status !== 403) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

function SessionLookupError({ message, retry }: { message: string; retry: () => void }) {
  return <Alert variant="destructive">
    <AlertTitle>暂时无法验证登录状态</AlertTitle>
    <AlertDescription>{message}<Button onClick={retry}>重试</Button></AlertDescription>
  </Alert>
}

function App() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { shouldShowDialog, fromVersion, toVersion, handleClose, handleRemindLater } = useVersionCheck()

  useEffect(() => {
    const handleAuthExpired = () => {
      queryClient.clear()
      navigate('/login', { replace: true })
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
    }
  }, [navigate, queryClient])

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
          <Route path="/" element={<SelfCheck />} />
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
            <Route path=":id/chunk-prune" element={<ServerChunkPrune />} />
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
