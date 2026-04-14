import { useSelector } from 'react-redux'

const PHASE_ORDER = [
  { key: 'spec', label: 'A. 게임 기획' },
  { key: 'planning', label: 'B. 에셋 계획' },
  { key: 'assets', label: 'C. 에셋 생성' },
  { key: 'map_design', label: 'D. 맵 설계' },
  { key: 'tile_generation', label: 'E. 타일 생성' },
  { key: 'event_plan', label: 'F. 이벤트 기획' },
  { key: 'event_compile', label: 'G. 이벤트 컴파일' },
  { key: 'integration', label: 'H. 프로젝트 조립' },
  { key: 'validation', label: 'I. 검증' },
]

function PhaseList({ completedPhases, currentPhase }) {
  return (
    <div className="space-y-1">
      {PHASE_ORDER.map(({ key, label }) => {
        const done = completedPhases.includes(key)
        const active = !done && key === currentPhase
        return (
          <div key={key} className="flex items-center gap-2 text-sm">
            <span className="w-4 text-center">
              {done ? '✓' : active ? '⟳' : '·'}
            </span>
            <span
              style={{
                color: done
                  ? 'var(--text-primary)'
                  : active
                    ? '#ffd60a'
                    : 'var(--text-secondary)',
                fontWeight: done || active ? 600 : 400,
              }}
            >
              {label}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function GenerationProgress() {
  const { status, progress, message, completedPhases, currentPhase, queuePosition, queueWaitSeconds } =
    useSelector((s) => s.generation)

  const isDone = ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(status)
  const isQueued = status === 'queued'

  if (isQueued) {
    return (
      <div className="space-y-6">
        <div className="text-center py-6">
          <p className="text-lg font-bold mb-2" style={{ color: '#eab308' }}>대기열 {queuePosition}번째</p>
          <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
            현재 다른 게임이 생성 중입니다
          </p>
          <p className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            약 {Math.ceil((queueWaitSeconds || 300) / 60)}분 대기
          </p>
          <p className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
            순서가 오면 자동으로 생성이 시작됩니다
          </p>
        </div>

        {/* 노드 현황 (아직 시작 전이라 전부 빈 상태) */}
        <div className="rounded-lg p-4" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
          <p className="text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>노드 실행 현황</p>
          <PhaseList completedPhases={[]} currentPhase="" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 진행률 바 */}
      <div>
        <div className="flex justify-between text-sm mb-2" style={{ color: 'var(--text-secondary)' }}>
          <span>{message || '생성 중...'}</span>
          <span>{progress}%</span>
        </div>
        <div className="w-full rounded-full h-2" style={{ background: 'var(--bg-tertiary)' }}>
          <div
            className="h-2 rounded-full transition-all duration-500"
            style={{
              width: `${progress}%`,
              background: status === 'failed' ? '#ff3b30' : 'var(--accent)',
            }}
          />
        </div>
      </div>

      {/* 노드 진행 현황 */}
      <div
        className="rounded-lg p-4"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
      >
        <p className="text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
          노드 실행 현황
        </p>
        <PhaseList completedPhases={completedPhases} currentPhase={currentPhase} />
      </div>

      {!isDone && (
        <p className="text-xs text-center" style={{ color: 'var(--text-secondary)' }}>
          게임 생성에는 약 5~10분이 소요됩니다.
        </p>
      )}
    </div>
  )
}
