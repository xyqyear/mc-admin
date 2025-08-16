import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from 'antd'
import { useHasToken } from '@/stores/useTokenStore'

// Layout Components
import AppHeader from '@/components/layout/AppHeader'
import AppSidebar from '@/components/layout/AppSidebar'

// Pages
import Login from '@/pages/Login'
import Home from '@/pages/Home'
import Overview from '@/pages/Overview'
import Backups from '@/pages/Backups'
import ServerDetail from '@/pages/server/[id]'
import ServerPlayers from '@/pages/server/[id]/players'
import ServerFiles from '@/pages/server/[id]/files'
import ServerWhitelist from '@/pages/server/[id]/whitelist'
import ServerArchive from '@/pages/server/[id]/archive'
import ServerCompose from '@/pages/server/[id]/compose'
import ServerNew from '@/pages/server/new'

const { Content } = Layout

// Protected Route component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const hasToken = useHasToken()
  
  if (!hasToken) {
    return <Navigate to="/login" replace />
  }
  
  return <>{children}</>
}

// Main Layout component
const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <Layout className="h-screen">
      <AppHeader />
      <Layout>
        <AppSidebar />
        <Layout>
          <Content className="p-4 overflow-auto">
            {children}
          </Content>
        </Layout>
      </Layout>
    </Layout>
  )
}

function App() {
  return (
    <Router
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <MainLayout>
                <Home />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/overview"
          element={
            <ProtectedRoute>
              <MainLayout>
                <Overview />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/backups"
          element={
            <ProtectedRoute>
              <MainLayout>
                <Backups />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/new"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerNew />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/:id"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerDetail />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/:id/players"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerPlayers />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/:id/files"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerFiles />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/:id/whitelist"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerWhitelist />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/:id/archive"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerArchive />
              </MainLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/server/:id/compose"
          element={
            <ProtectedRoute>
              <MainLayout>
                <ServerCompose />
              </MainLayout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </Router>
  )
}

export default App
