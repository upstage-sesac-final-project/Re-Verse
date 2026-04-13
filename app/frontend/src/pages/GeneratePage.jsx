import { useEffect } from 'react'
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

  useEffect(() => {
    if (projects.length === 0) dispatch(fetchProjects())
  }, [dispatch, projects.length])

  // 언마운트 시 상태 초기화
  useEffect(() => {
    return () => {
      dispatch(reset())
    }
  }, [dispatch])

  function handleSubmit({ prompt, options }) {
    dispatch(startGeneration({ projectId: Number(projectId), prompt, options }))
  }

  function handleRetry() {
    dispatch(reset())
  }

  function handleGoToEditor() {
    navigate(`/editor/${projectId}`)
  }

  const isIdle = status === 'idle'
  const isInProgress = ['starting', 'in_progress'].includes(status)
  const isDone = ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(status)

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header />
      <main className="max-w-xl mx-auto px-4 py-10">
        {/* 헤더 */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/dashboard')}
            className="text-sm mb-4 flex items-center gap-1"
            style={{ color: 'var(--text-secondary)' }}
          >
            ← 대시보드
          </button>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            AI 게임 생성
          </h1>
          {project && (
            <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
              프로젝트: {project.name}
            </p>
          )}
        </div>

        {/* 컨텐츠 패널 */}
        <div
          className="rounded-xl p-6"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
        >
          {isIdle && (
            <GenerationForm onSubmit={handleSubmit} isLoading={false} />
          )}

          {isInProgress && (
            <GenerationProgress onDone={() => {}} />
          )}

          {isDone && (
            <GenerationResult onRetry={handleRetry} onGoToEditor={handleGoToEditor} />
          )}
        </div>
      </main>
    </div>
  )
}
