import { useSelector } from 'react-redux'

export default function GenerationResult({ onRetry, onGoToEditor }) {
  const { status, finalMessage, error, validationErrors, validationWarnings, completedPhases } =
    useSelector((s) => s.generation)

  const isSuccess = status === 'completed' || status === 'completed_with_warnings'
  const isFailed = status === 'failed'

  return (
    <div className="space-y-5">
      {/* 상태 헤더 */}
      <div
        className="rounded-lg p-4 text-center"
        style={{
          background: isSuccess ? 'rgba(52,199,89,0.1)' : 'rgba(255,59,48,0.1)',
          border: `1px solid ${isSuccess ? '#34c759' : '#ff3b30'}`,
        }}
      >
        <p className="text-2xl mb-1">{isSuccess ? '✓' : '✗'}</p>
        <p
          className="font-semibold text-sm"
          style={{ color: isSuccess ? '#34c759' : '#ff3b30' }}
        >
          {isSuccess ? '게임 생성 완료' : '생성 실패'}
        </p>
        {(finalMessage || error) && (
          <p className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
            {finalMessage || error}
          </p>
        )}
      </div>

      {/* 완료 노드 */}
      {completedPhases.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
        >
          <p className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
            완료된 단계 ({completedPhases.length}/10)
          </p>
          <p className="text-xs" style={{ color: 'var(--text-primary)' }}>
            {completedPhases.join(' → ')}
          </p>
        </div>
      )}

      {/* 검증 오류 */}
      {validationErrors.length > 0 && (
        <div
          className="rounded-lg p-3"
          style={{ background: 'rgba(255,59,48,0.08)', border: '1px solid #ff3b30' }}
        >
          <p className="text-xs font-semibold mb-2" style={{ color: '#ff3b30' }}>
            검증 오류 ({validationErrors.length}건)
          </p>
          <ul className="space-y-1">
            {validationErrors.map((e, i) => (
              <li key={i} className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 액션 버튼 */}
      <div className="flex gap-3">
        {isSuccess && (
          <button
            onClick={onGoToEditor}
            className="flex-1 py-3 rounded-lg font-semibold text-sm"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            게임 플레이 →
          </button>
        )}
        <button
          onClick={onRetry}
          className="flex-1 py-3 rounded-lg font-semibold text-sm"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        >
          {isFailed ? '다시 시도' : '새로 생성'}
        </button>
      </div>
    </div>
  )
}
