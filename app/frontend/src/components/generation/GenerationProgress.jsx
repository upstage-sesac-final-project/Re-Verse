import { useEffect, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { wsEventReceived, fetchGenerationStatus } from '../../store/generationSlice'

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

const WS_BASE =
  (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host

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

export default function GenerationProgress({ onDone }) {
  const dispatch = useDispatch()
  const { generationId, wsUrl, status, progress, message, completedPhases, currentPhase } =
    useSelector((s) => s.generation)

  const wsRef = useRef(null)
  const pollingRef = useRef(null)

  useEffect(() => {
    if (!generationId || !wsUrl) return

    // WebSocket 연결
    const ws = new WebSocket(`${WS_BASE}${wsUrl}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data)
        dispatch(wsEventReceived(evt))
        if (['completed', 'completed_with_warnings', 'error'].includes(evt.type)) {
          onDone?.()
        }
      } catch {
        // JSON 파싱 오류 무시
      }
    }

    ws.onerror = () => {
      // WS 실패 시 폴링 fallback
      ws.close()
      startPolling()
    }

    ws.onclose = () => {
      wsRef.current = null
    }

    return () => {
      ws.close()
      clearInterval(pollingRef.current)
    }
  }, [generationId, wsUrl]) // eslint-disable-line react-hooks/exhaustive-deps

  function startPolling() {
    pollingRef.current = setInterval(async () => {
      const result = await dispatch(fetchGenerationStatus(generationId))
      const s = result.payload?.status
      if (['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(s)) {
        clearInterval(pollingRef.current)
        onDone?.()
      }
    }, 3000)
  }

  const isDone = ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(status)

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
