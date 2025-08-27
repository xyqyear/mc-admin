
import { App as AntdApp } from 'antd'
import React, { ErrorInfo, Suspense } from 'react'
import { ErrorBoundary } from 'react-error-boundary'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { ErrorFallback } from './components/layout/ErrorFallback'
import { LoadingSpinner } from './components/layout/LoadingSpinner'
import { MainLayout } from './components/layout/MainLayout'
import { useTokenStore } from './stores/useTokenStore'

// Lazy load pages for better performance
const Login = React.lazy(() => import('./pages/Login'))
const Home = React.lazy(() => import('./pages/Home'))
const Overview = React.lazy(() => import('./pages/Overview'))
const Backups = React.lazy(() => import('./pages/Backups'))
const ServerNew = React.lazy(() => import('./pages/server/new'))
const ServerDetail = React.lazy(() => import('./pages/server/[id]'))
const ServerPlayers = React.lazy(() => import('./pages/server/[id]/players'))
const ServerFiles = React.lazy(() => import('./pages/server/[id]/files'))
const ServerWhitelist = React.lazy(() => import('./pages/server/[id]/whitelist'))
const ServerArchive = React.lazy(() => import('./pages/server/[id]/archive'))
const ServerCompose = React.lazy(() => import('./pages/server/[id]/compose'))



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
          <Route path="/backups" element={<Backups />} />
          <Route path="/server">
            <Route path="new" element={<ServerNew />} />
            <Route path=":id" element={<ServerDetail />} />
            <Route path=":id/players" element={<ServerPlayers />} />
            <Route path=":id/files" element={<ServerFiles />} />
            <Route path=":id/whitelist" element={<ServerWhitelist />} />
            <Route path=":id/archive" element={<ServerArchive />} />
            <Route path=":id/compose" element={<ServerCompose />} />
          </Route>
        </Route>

        {/* Catch all route */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}

export default App
