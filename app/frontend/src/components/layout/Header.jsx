import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'
import { logoutUser } from '../../store/userSlice'

export default function Header() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { isAuthenticated, user } = useSelector((s) => s.user)

  async function handleLogout() {
    await dispatch(logoutUser())
    navigate('/login', { replace: true })
  }

  return (
    <header
      className="h-14 flex items-center justify-between px-6 flex-shrink-0"
      style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}
    >
      <Link to={isAuthenticated ? '/dashboard' : '/'} className="flex items-center gap-3">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm"
          style={{ background: 'var(--accent)' }}
        >
          R
        </div>
        <span className="font-semibold text-lg" style={{ color: 'var(--text-primary)' }}>
          Re:Verse
        </span>
      </Link>

      <div className="flex items-center gap-3">
        {isAuthenticated ? (
          <>
            {user?.isAdmin && (
              <Link
                to="/admin"
                className="text-xs px-2 py-1 rounded-full font-medium"
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                관리자
              </Link>
            )}
            <Link
              to="/dashboard"
              className="text-xs px-3 py-1.5 rounded-lg"
              style={{ color: 'var(--text-secondary)' }}
            >
              내 프로젝트
            </Link>
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {user?.username}
            </span>
            <button
              onClick={handleLogout}
              className="text-xs px-3 py-1.5 rounded-lg"
              style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              로그아웃
            </button>
          </>
        ) : (
          <>
            <Link
              to="/login"
              className="text-xs px-3 py-1.5 rounded-lg"
              style={{ color: 'var(--text-secondary)' }}
            >
              로그인
            </Link>
            <Link
              to="/register"
              className="text-xs px-3 py-1.5 rounded-lg font-medium"
              style={{ background: 'var(--accent)', color: '#fff' }}
            >
              회원가입
            </Link>
          </>
        )}
      </div>
    </header>
  )
}
