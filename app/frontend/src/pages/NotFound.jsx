import { Link } from 'react-router-dom'
import Tetris from '../components/common/Tetris'

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 gap-6" style={{ background: 'var(--bg-primary)' }}>
      <div className="text-center">
        <p className="text-5xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>404</p>
        <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>페이지를 찾을 수 없습니다</p>
        <Link to="/" className="text-xs font-medium" style={{ color: 'var(--accent)' }}>홈으로 돌아가기</Link>
      </div>
      <Tetris />
    </div>
  )
}
