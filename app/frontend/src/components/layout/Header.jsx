import { useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'
import { logoutUser } from '../../store/userSlice'
import BugReportModal from '../common/BugReportModal'

export default function Header() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { isAuthenticated, user } = useSelector((s) => s.user)
  const currentProject = useSelector((s) => s.game.currentProject)
  const [bugOpen, setBugOpen] = useState(false)

  async function handleLogout() {
    await dispatch(logoutUser())
    navigate('/login', { replace: true })
  }

  return (
    <>
    <header
      className="h-12 flex items-center justify-between px-4 flex-shrink-0"
      style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-4">
        <Link to={isAuthenticated ? '/dashboard' : '/'} className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center text-white font-bold text-xs" style={{ background: 'var(--accent)' }}>R</div>
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Re:Verse</span>
        </Link>
        {currentProject && (
          <>
            <span style={{ color: 'var(--border)' }}>/</span>
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{currentProject.name}</span>
          </>
        )}
      </div>

      <nav className="flex items-center gap-1">
        {isAuthenticated ? (
          <>
            {user?.isAdmin && (
              <Link to="/admin" className="text-xs px-2 py-1 rounded-md font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>관리자</Link>
            )}
            <button onClick={() => setBugOpen(true)} className="re-nav-link text-xs px-2.5 py-1" style={{ color: 'var(--text-secondary)' }}>버그리포트</button>
            <Link to="/docs" className="re-nav-link text-xs px-2.5 py-1" style={{ color: 'var(--text-secondary)' }}>문서</Link>
            <Link to="/dashboard" className="re-nav-link text-xs px-2.5 py-1" style={{ color: 'var(--text-secondary)' }}>프로젝트</Link>
            <button onClick={handleLogout} className="re-nav-link text-xs px-2.5 py-1" style={{ color: 'var(--text-secondary)' }}>로그아웃</button>
          </>
        ) : (
          <>
            <Link to="/docs" className="re-nav-link text-xs px-2.5 py-1" style={{ color: 'var(--text-secondary)' }}>문서</Link>
            <Link to="/login" className="re-nav-link text-xs px-2.5 py-1" style={{ color: 'var(--text-secondary)' }}>로그인</Link>
            <Link to="/register" className="text-xs px-2.5 py-1 rounded-md font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>시작하기</Link>
          </>
        )}
      </nav>
    </header>
    {bugOpen && <BugReportModal onClose={() => setBugOpen(false)} />}
    </>
  )
}
