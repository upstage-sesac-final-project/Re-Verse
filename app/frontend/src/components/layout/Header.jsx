import { useState, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'
import { logoutUser } from '../../store/userSlice'
import BugReportModal from '../common/BugReportModal'
import NoticeModal from '../common/NoticeModal'

export default function Header() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { isAuthenticated, user } = useSelector((s) => s.user)
  const currentProject = useSelector((s) => s.game.currentProject)
  const [bugOpen, setBugOpen] = useState(false)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [hasNew, setHasNew] = useState(false)

  useEffect(() => {
    fetch('/api/v1/notices/latest-version')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.version && data.version !== localStorage.getItem('re-verse:seen-version')) {
          setHasNew(true)
        }
      })
      .catch(() => {})
  }, [])

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

      <nav className="flex items-center gap-1.5">
        {isAuthenticated ? (
          <>
            {user?.isAdmin && (
              <Link to="/admin" className="text-xs px-2.5 py-1.5 rounded-md font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>관리자</Link>
            )}
            <button onClick={() => setNoticeOpen(true)} className="re-nav-link text-xs px-2.5 py-1.5 rounded-md relative"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>
              공지
              {hasNew && <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent)' }} />}
            </button>
            <button onClick={() => setBugOpen(true)} className="re-nav-link text-xs px-2.5 py-1.5 rounded-md"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>버그리포트</button>
            <Link to="/docs" className="re-nav-link text-xs px-2.5 py-1.5 rounded-md"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>가이드</Link>
            <Link to="/dashboard" className="re-nav-link text-xs px-2.5 py-1.5 rounded-md"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>프로젝트</Link>
            <div className="flex items-center gap-1.5 ml-1 pl-2" style={{ borderLeft: '1px solid var(--border)' }}>
              <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{ background: 'var(--accent)', color: '#fff' }}>
                {(user?.username || '?')[0].toUpperCase()}
              </div>
              <span className="text-xs" style={{ color: 'var(--text-primary)' }}>{user?.username}</span>
            </div>
            <button onClick={handleLogout} className="re-nav-link text-xs px-2.5 py-1.5 rounded-md"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>로그아웃</button>
          </>
        ) : (
          <>
            <Link to="/docs" className="re-nav-link text-xs px-2.5 py-1.5 rounded-md"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>가이드</Link>
            <Link to="/login" className="re-nav-link text-xs px-2.5 py-1.5 rounded-md"
              style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.04)' }}>로그인</Link>
            <Link to="/register" className="text-xs px-3 py-1.5 rounded-md font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>시작하기</Link>
          </>
        )}
      </nav>
    </header>
    {bugOpen && <BugReportModal onClose={() => setBugOpen(false)} />}
    {noticeOpen && <NoticeModal onClose={() => { setNoticeOpen(false); setHasNew(false) }} />}
    </>
  )
}
