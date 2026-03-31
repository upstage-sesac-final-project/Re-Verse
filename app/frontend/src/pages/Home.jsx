import { useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()
  const { isAuthenticated } = useSelector((s) => s.user)

  function handleStart() {
    navigate(isAuthenticated ? '/dashboard' : '/login')
  }

  return (
    <div
      className="flex flex-col items-center justify-center h-screen"
      style={{ background: 'var(--bg-primary)' }}
    >
      <h1 className="text-5xl font-bold mb-4" style={{ color: 'var(--text-primary)' }}>Re:Verse</h1>
      <p className="text-lg mb-8" style={{ color: 'var(--text-secondary)' }}>
        자연어로 RPG 게임을 만들어보세요
      </p>
      <button
        onClick={handleStart}
        className="px-8 py-3 text-white text-lg rounded-lg font-semibold"
        style={{ background: 'var(--accent)' }}
      >
        시작하기
      </button>
      {!isAuthenticated && (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          계정이 없으신가요?{' '}
          <Link to="/register" className="underline" style={{ color: 'var(--accent)' }}>
            회원가입
          </Link>
        </p>
      )}
    </div>
  )
}
