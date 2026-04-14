import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Provider, useDispatch, useSelector } from 'react-redux'
import { Analytics } from '@vercel/analytics/react'
import { store } from './store'
import { initAuth, logoutUser } from './store/userSlice'
import ProtectedRoute from './components/common/ProtectedRoute'
import AdminRoute from './components/common/AdminRoute'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import GameEditor from './pages/GameEditor'
// GeneratePage removed — generation is now inline in Dashboard
import Admin from './pages/Admin'
import Docs from './pages/Docs'
import NotFound from './pages/NotFound'

function AppRoutes() {
  const dispatch = useDispatch()
  const { isAuthenticated, isLoading } = useSelector((s) => s.user)

  useEffect(() => {
    dispatch(initAuth())
  }, [dispatch])

  useEffect(() => {
    function handleSessionExpired() {
      dispatch(logoutUser())
    }
    window.addEventListener('auth:session-expired', handleSessionExpired)
    return () => window.removeEventListener('auth:session-expired', handleSessionExpired)
  }, [dispatch])

  return (
    <Routes>
      <Route
        path="/"
        element={
          isLoading ? null : isAuthenticated ? (
            <Navigate to="/dashboard" replace />
          ) : (
            <Home />
          )
        }
      />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/editor/:projectId"
        element={
          <ProtectedRoute>
            <GameEditor />
          </ProtectedRoute>
        }
      />
      {/* generate route removed — handled in Dashboard */}
      <Route
        path="/admin"
        element={
          <AdminRoute>
            <Admin />
          </AdminRoute>
        }
      />
      <Route path="/docs" element={<Docs />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default function App() {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <AppRoutes />
        <Analytics />
      </BrowserRouter>
    </Provider>
  )
}
