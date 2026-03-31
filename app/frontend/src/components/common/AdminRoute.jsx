import { useSelector } from 'react-redux'
import { Navigate, useLocation } from 'react-router-dom'

export default function AdminRoute({ children }) {
  const { isAuthenticated, isLoading, user } = useSelector((s) => s.user)
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ background: 'var(--bg-primary)' }}>
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>로딩 중...</span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname)}`} replace />
  }

  if (!user?.isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}
