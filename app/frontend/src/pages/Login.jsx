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

  // 이미 로그인 상태면 대시보드로
  if (isAuthenticated) {
    return <Navigate to={getSafeRedirect()} replace />
  }

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
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--bg-primary)' }}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-8"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-8">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            R
          </div>
          <span className="font-semibold text-lg" style={{ color: 'var(--text-primary)' }}>
            Re:Verse
          </span>
        </div>

        <h1 className="text-xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
          로그인
        </h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
          계정에 접속하세요
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="email" className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
              이메일
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              autoComplete="email"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
              비밀번호
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          {error && (
            <p className="text-xs" style={{ color: '#f87171' }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg text-sm font-semibold mt-1 disabled:opacity-50"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <p className="text-center text-xs mt-6" style={{ color: 'var(--text-secondary)' }}>
          계정이 없으신가요?{' '}
          <Link to="/register" className="underline" style={{ color: 'var(--accent)' }}>
            회원가입
          </Link>
        </p>
      </div>
    </div>
  )
}
