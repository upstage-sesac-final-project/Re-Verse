import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6" style={{ background: 'var(--bg-primary)' }}>
      <p className="text-6xl font-bold mb-3" style={{ color: 'var(--text-primary)' }}>404</p>
      <p className="text-sm mb-8" style={{ color: 'var(--text-secondary)' }}>페이지를 찾을 수 없습니다</p>
      <Link to="/" className="text-sm font-medium" style={{ color: 'var(--accent)' }}>
        홈으로 돌아가기
      </Link>
    </div>
  )
}
