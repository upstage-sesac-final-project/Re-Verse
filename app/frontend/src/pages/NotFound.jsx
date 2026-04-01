import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <div
      className="flex flex-col items-center justify-center h-screen"
      style={{ background: 'var(--bg-primary)' }}
    >
      <h1 className="text-8xl font-bold mb-4" style={{ color: 'var(--accent)' }}>404</h1>
      <p className="text-xl mb-8" style={{ color: 'var(--text-secondary)' }}>페이지를 찾을 수 없습니다</p>
      <button
        onClick={() => navigate('/')}
        className="px-6 py-3 rounded-lg text-sm font-semibold"
        style={{ background: 'var(--accent)', color: '#fff' }}
      >
        홈으로 돌아가기
      </button>
    </div>
  )
}
