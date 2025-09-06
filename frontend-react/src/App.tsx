
import { App as AntdApp } from 'antd'
import React, { ErrorInfo, Suspense } from 'react'
import { ErrorBoundary } from 'react-error-boundary'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { ErrorFallback } from '@/components/layout/ErrorFallback'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import { MainLayout } from '@/components/layout/MainLayout'
import { useTokenStore } from '@/stores/useTokenStore'

// Lazy load pages for better performance
const Login = React.lazy(() => import('@/pages/Login'))
const Home = React.lazy(() => import('@/pages/Home'))
const Overview = React.lazy(() => import('@/pages/Overview'))
const Snapshots = React.lazy(() => import('@/pages/Snapshots'))
const ServerNew = React.lazy(() => import('@/pages/server/ServerNew'))
const ServerDetail = React.lazy(() => import('@/pages/server/servers/ServerDetail'))
const ServerFiles = React.lazy(() => import('@/pages/server/servers/ServerFiles'))
const ServerCompose = React.lazy(() => import('@/pages/server/servers/ServerCompose'))
const ServerConsole = React.lazy(() => import('@/pages/server/servers/ServerConsole'))
const UserManagement = React.lazy(() => import('@/pages/admin/UserManagement'))



// Protected route wrapper using React Router 6 outlet pattern
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

// Auth route wrapper (redirects to home if already authenticated)
function AuthRoutes() {
  const token = useTokenStore((state) => state.token)

  if (token) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

function App() {
  const { notification } = AntdApp.useApp()

  // Global error handler
  const handleError = (error: Error, errorInfo: ErrorInfo) => {
    console.error('Application error:', error, errorInfo)
    notification.error({
      message: 'Application Error',
      description: 'An unexpected error occurred. Please refresh the page.',
      duration: 0,
    })
  }

  return (
    <ErrorBoundary FallbackComponent={ErrorFallback} onError={handleError}>
      <Routes>
        {/* Public routes */}
        <Route element={<AuthRoutes />}>
          <Route path="/login" element={
            <Suspense fallback={<LoadingSpinner fullscreen />}>
              <Login />
            </Suspense>
          } />
        </Route>

        {/* Protected routes with nested structure */}
        <Route element={<ProtectedRoutes />}>
          <Route path="/" element={<Home />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/snapshots" element={<Snapshots />} />
          <Route path="/server">
            <Route path="new" element={<ServerNew />} />
            <Route path=":id" element={<ServerDetail />} />
            <Route path=":id/files" element={<ServerFiles />} />
            <Route path=":id/compose" element={<ServerCompose />} />
            <Route path=":id/console" element={<ServerConsole />} />
          </Route>
          <Route path="/admin">
            <Route path="users" element={<UserManagement />} />
          </Route>
        </Route>

        {/* Catch all route */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}

export default App
