import { useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'

const FEATURES = [
  {
    icon: '✦',
    title: '자연어 명령',
    desc: '복잡한 편집기 없이 말하듯 설명하면 AI가 게임 요소를 만들어줍니다.',
  },
  {
    icon: '⟳',
    title: '즉시 미리보기',
    desc: 'AI가 생성한 캐릭터, 아이템, 맵을 바로 게임에서 확인할 수 있습니다.',
  },
  {
    icon: '◈',
    title: '다양한 요소 지원',
    desc: '캐릭터, 적, 스킬, 아이템, 맵, 이벤트 등 RPG Maker MZ 전 요소를 지원합니다.',
  },
]

export default function Home() {
  const navigate = useNavigate()
  const { isAuthenticated } = useSelector((s) => s.user)

  function handleStart() {
    navigate(isAuthenticated ? '/dashboard' : '/login')
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6"
      style={{ background: 'var(--bg-primary)' }}
    >
      <div className="text-center max-w-xl w-full">
        {/* 로고 뱃지 */}
        <div className="flex justify-center mb-6">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center text-white font-bold text-2xl"
            style={{ background: 'var(--accent)' }}
          >
            R
          </div>
        </div>

        <h1 className="text-5xl font-bold mb-3 tracking-tight" style={{ color: 'var(--text-primary)' }}>
          Re:Verse
        </h1>
        <p className="text-base mb-10" style={{ color: 'var(--text-secondary)' }}>
          자연어로 RPG 게임을 만들어보세요
        </p>

        <div className="grid grid-cols-1 gap-3 mb-10 text-left sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="re-card rounded-xl p-4"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            >
              <span className="text-xl mb-2 block" style={{ color: 'var(--accent)' }}>{f.icon}</span>
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                {f.title}
              </p>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>

        <button
          onClick={handleStart}
          className="re-btn-primary px-8 py-3 text-white text-sm rounded-lg font-semibold"
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
            {' '}·{' '}
            <Link to="/docs" className="underline" style={{ color: 'var(--accent)' }}>
              사용자 가이드
            </Link>
          </p>
        )}
      </div>
    </div>
  )
}
