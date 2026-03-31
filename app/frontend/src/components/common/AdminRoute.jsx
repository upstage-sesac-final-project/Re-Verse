import { useSelector } from 'react-redux'
import { Navigate } from 'react-router-dom'

export default function AdminRoute({ children }) {
  const { isAuthenticated, isLoading, user } = useSelector((s) => s.user)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ background: 'var(--bg-primary)' }}>
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>로딩 중...</span>
      </div>
    )
  }

  if (!isAuthenticated || !user?.isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}
