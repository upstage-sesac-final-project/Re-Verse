import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Provider, useDispatch, useSelector } from 'react-redux'
import { Analytics } from '@vercel/analytics/react'
import { store } from './store'
import { initAuth } from './store/userSlice'
import ProtectedRoute from './components/common/ProtectedRoute'
import AdminRoute from './components/common/AdminRoute'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import GameEditor from './pages/GameEditor'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'

function AppRoutes() {
  const dispatch = useDispatch()
  const { isAuthenticated, isLoading } = useSelector((s) => s.user)

  useEffect(() => {
    dispatch(initAuth())
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
      <Route
        path="/admin"
        element={
          <AdminRoute>
            <Admin />
          </AdminRoute>
        }
      />
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
