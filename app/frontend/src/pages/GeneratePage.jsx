import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { fetchProjects } from '../store/gameSlice'
import { startGeneration, reset } from '../store/generationSlice'
import Header from '../components/layout/Header'
import GenerationForm from '../components/generation/GenerationForm'
import GenerationProgress from '../components/generation/GenerationProgress'
import GenerationResult from '../components/generation/GenerationResult'

export default function GeneratePage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const dispatch = useDispatch()

  const { projects } = useSelector((s) => s.game)
  const { status } = useSelector((s) => s.generation)

  const project = projects.find((p) => String(p.id) === projectId)
  const isIdle = status === 'idle'
  const isInProgress = ['starting', 'in_progress'].includes(status)
  const isDone = ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(status)

  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const [pendingPath, setPendingPath] = useState(null)

  useEffect(() => {
    if (projects.length === 0) dispatch(fetchProjects())
  }, [dispatch, projects.length])

  // 언마운트 시에만 reset (status 변경 시 re-run 안 함)
  useEffect(() => {
    return () => { dispatch(reset()) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 생성 중 브라우저 이탈 방지 (새로고침, 탭 닫기)
  useEffect(() => {
    if (!isInProgress) return
    const handler = (e) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isInProgress])

  // 생성 중 navigate 감싸기
  function safeNavigate(path) {
    if (isInProgress) {
      setPendingPath(path)
      setShowLeaveModal(true)
    } else {
      navigate(path)
    }
  }

  function confirmLeave() {
    setShowLeaveModal(false)
    if (pendingPath) navigate(pendingPath)
  }

  function handleSubmit({ prompt, options }) {
    dispatch(startGeneration({ projectId: Number(projectId), prompt, options }))
  }

  function handleRetry() {
    dispatch(reset())
  }

  function handleGoToEditor() {
    navigate(`/editor/${projectId}`)
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header />
      <main className="max-w-xl mx-auto px-4 py-8">
        <div className="mb-6">
          <button onClick={() => safeNavigate('/dashboard')}
            className="text-xs mb-3 flex items-center gap-1 transition-colors hover:text-white"
            style={{ color: 'var(--text-secondary)' }}>
            ← 프로젝트 목록
          </button>
          <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
            세계 생성
          </h1>
          {project && (
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{project.name}</p>
          )}
        </div>

        <div className="rounded-lg p-5" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
          {isIdle && <GenerationForm onSubmit={handleSubmit} isLoading={false} />}
          {isInProgress && <GenerationProgress onDone={() => {}} />}
          {isDone && <GenerationResult onRetry={handleRetry} onGoToEditor={handleGoToEditor} />}
        </div>
      </main>

      {/* 생성 중 이탈 확인 모달 */}
      {showLeaveModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="rounded-xl p-6 max-w-sm w-full mx-4" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
            <h3 className="text-sm font-bold mb-2" style={{ color: 'var(--text-primary)' }}>게임 생성 중입니다</h3>
            <p className="text-xs mb-5" style={{ color: 'var(--text-secondary)' }}>
              페이지를 떠나면 진행 상황을 확인할 수 없습니다. 생성은 백그라운드에서 계속됩니다.
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowLeaveModal(false)}
                className="px-3 py-1.5 text-xs rounded-lg font-medium"
                style={{ background: 'var(--accent)', color: '#fff' }}>
                머무르기
              </button>
              <button onClick={confirmLeave}
                className="px-3 py-1.5 text-xs rounded-lg"
                style={{ color: 'var(--text-secondary)' }}>
                떠나기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
