import { useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { loginUser } from '../store/userSlice'

export default function Login() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { isAuthenticated } = useSelector((s) => s.user)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function getSafeRedirect() {
    const raw = searchParams.get('redirect') || '/dashboard'
    return raw.startsWith('/') && !raw.startsWith('//') ? raw : '/dashboard'
  }

  if (isAuthenticated) return <Navigate to={getSafeRedirect()} replace />

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    const result = await dispatch(loginUser({ email, password }))
    setLoading(false)
    if (loginUser.rejected.match(result)) {
      setError(result.payload || '로그인에 실패했습니다.')
    } else {
      navigate(getSafeRedirect(), { replace: true })
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6" style={{ background: 'var(--bg-primary)' }}>
      <div className="w-full max-w-xs">
        <Link to="/" className="flex items-center gap-2 mb-12">
          <div className="w-6 h-6 rounded-md flex items-center justify-center text-white font-bold text-xs" style={{ background: 'var(--accent)' }}>R</div>
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Re:Verse</span>
        </Link>

        <h1 className="text-lg font-bold mb-8" style={{ color: 'var(--text-primary)' }}>로그인</h1>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="email" className="block text-xs mb-1.5" style={{ color: 'var(--text-secondary)' }}>이메일</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              required autoFocus autoComplete="email"
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-colors"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs mb-1.5" style={{ color: 'var(--text-secondary)' }}>비밀번호</label>
            <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              required autoComplete="current-password"
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-colors"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
          </div>

          {error && <p className="text-xs" style={{ color: '#f87171' }}>{error}</p>}

          <button type="submit" disabled={loading}
            className="re-btn-primary w-full py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 mt-1"
            style={{ background: 'var(--accent)', color: '#fff' }}>
            {loading ? '접속 중...' : '로그인'}
          </button>
        </form>

        <p className="text-xs mt-8" style={{ color: 'var(--text-secondary)' }}>
          계정이 없으신가요?{' '}
          <Link to="/register" className="font-medium" style={{ color: 'var(--accent)' }}>회원가입</Link>
        </p>
      </div>
    </div>
  )
}
