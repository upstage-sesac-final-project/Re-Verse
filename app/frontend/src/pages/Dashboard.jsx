import { useEffect, useState, useRef, useCallback } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { fetchProjects, createProject, deleteProject, setCurrentProject } from '../store/gameSlice'
import { startGeneration, reset, wsEventReceived, fetchGenerationStatus, fetchActiveGeneration } from '../store/generationSlice'
import Header from '../components/layout/Header'
import Modal from '../components/common/Modal'
import GenerationForm from '../components/generation/GenerationForm'
import GenerationProgress from '../components/generation/GenerationProgress'
import GenerationResult from '../components/generation/GenerationResult'

function relativeTime(dateStr) {
  const utcStr = dateStr && !dateStr.endsWith('Z') && !dateStr.includes('+') ? dateStr + 'Z' : dateStr
  const diff = Date.now() - new Date(utcStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '방금 전'
  if (minutes < 60) return `${minutes}분 전`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}시간 전`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}일 전`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}개월 전`
  return `${Math.floor(months / 12)}년 전`
}

export default function Dashboard() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { projects, isLoading } = useSelector((s) => s.game)
  const gen = useSelector((s) => s.generation)

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [createError, setCreateError] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  // 생성 모달: 'form' | 'progress' | 'result' | null
  const [genModal, setGenModal] = useState(null)
  const [genProjectId, setGenProjectId] = useState(null)

  const wsRef = useRef(null)
  const pollingRef = useRef(null)
  const WS_BASE = useRef(
    import.meta.env.VITE_WS_URL || ((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host)
  ).current

  useEffect(() => {
    dispatch(setCurrentProject(null))
    dispatch(fetchProjects())
  }, [dispatch])

  // cleanup 헬퍼
  function cleanupWs() {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
  }
  function cleanupPolling() {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }

  // polling: 진행률 + 대기열 + 완료 감지 (WS 불가 시 fallback, 5초 간격)
  function startPolling(genId) {
    if (pollingRef.current) return
    pollingRef.current = setInterval(async () => {
      const result = await dispatch(fetchGenerationStatus(genId))
      const s = result.payload?.status
      if (['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(s)) {
        cleanupPolling()
      }
    }, 5000)
  }

  // WS 연결 (JWT 토큰 포함)
  function connectWs(genId, wsUrl) {
    cleanupWs()
    const token = sessionStorage.getItem('access_token')
    if (!token) { startPolling(genId); return }
    const sep = wsUrl.includes('?') ? '&' : '?'
    const ws = new WebSocket(`${WS_BASE}${wsUrl}${sep}token=${token}`)
    wsRef.current = ws

    ws.onopen = () => {
      // WS 연결 성공하면 polling 중지 (WS가 실시간 업데이트 담당)
      cleanupPolling()
    }
    ws.onmessage = (e) => {
      try { dispatch(wsEventReceived(JSON.parse(e.data))) } catch {}
    }
    ws.onerror = () => { ws.close() }
    ws.onclose = () => {
      wsRef.current = null
      // WS 끊기면 완료 감지용 polling만 시작
      startPolling(genId)
    }
  }

  // 새 generation 시작 시: WS 연결
  useEffect(() => {
    if (!gen.generationId || !gen.wsUrl) return
    cleanupPolling()
    connectWs(gen.generationId, gen.wsUrl)
    return () => { cleanupWs(); cleanupPolling() }
  }, [gen.generationId, gen.wsUrl]) // eslint-disable-line react-hooks/exhaustive-deps

  // Dashboard 마운트 시: Redux에 생성 상태가 있으면 WS 재연결, 없으면 프로젝트별 활성 generation 조회
  useEffect(() => {
    if (['starting', 'queued', 'in_progress'].includes(gen.status) && gen.generationId) {
      // Redux에 상태 남아있음 (같은 세션, 페이지 이동 후 복귀)
      if (gen.wsUrl) connectWs(gen.generationId, gen.wsUrl)
      else startPolling(gen.generationId)
    } else if (gen.status === 'idle' && projects.length > 0) {
      // 새로고침 후 — 각 프로젝트에 활성 generation이 있는지 서버에 확인
      projects.forEach((p) => dispatch(fetchActiveGeneration(p.id)))
    }
    return () => { cleanupPolling() }
  }, [projects.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // gen status 변경 시 모달 상태 동기화
  useEffect(() => {
    if (!genProjectId || gen.projectId !== genProjectId) return
    if (['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(gen.status)) {
      setGenModal('result')
    }
    // queued → in_progress 전환 시 모달이 열려있으면 progress로 변경
    if (gen.status === 'in_progress' && genModal === 'progress') {
      // 이미 progress 모달이므로 자동으로 진행률 바로 전환됨 (GenerationProgress가 status 읽음)
    }
  }, [gen.status, gen.projectId, genProjectId, genModal])

  async function handleCreate(e) {
    e.preventDefault()
    if (!newName.trim()) return
    setCreateError('')
    setCreateLoading(true)
    const result = await dispatch(createProject({ name: newName.trim(), description: '' }))
    setCreateLoading(false)
    if (createProject.rejected.match(result)) {
      setCreateError(result.payload || '프로젝트 생성에 실패했습니다.')
    } else {
      setCreating(false)
      setNewName('')
      // 생성 후 AI 생성 모달 열기
      openGenForm(result.payload.id)
    }
  }

  function handleEdit(project) {
    dispatch(setCurrentProject(project))
    navigate(`/editor/${String(project.id)}`)
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return
    setDeleteLoading(true)
    setDeleteError('')
    const result = await dispatch(deleteProject(deleteTarget.id))
    setDeleteLoading(false)
    if (deleteProject.rejected.match(result)) {
      setDeleteError(result.payload || '삭제에 실패했습니다.')
    } else {
      setDeleteTarget(null)
      setDeleteError('')
    }
  }

  function openGenForm(projectId) {
    dispatch(reset())
    setGenProjectId(projectId)
    setGenModal('form')
  }

  function handleGenSubmit({ prompt, options }) {
    dispatch(startGeneration({ projectId: Number(genProjectId), prompt, options }))
    setGenModal('progress')
  }

  function handleGenRetry() {
    dispatch(reset())
    setGenModal('form')
  }

  function handleGenDone() {
    // progress → result 전환은 useEffect에서 처리
  }

  function closeGenModal() {
    const isRunning = ['starting', 'queued', 'in_progress'].includes(gen.status) && gen.projectId === genProjectId
    if (isRunning) {
      // 진행 중이면 모달만 닫고 상태 유지
      setGenModal(null)
    } else {
      setGenModal(null)
      setGenProjectId(null)
      dispatch(reset())
    }
  }

  function handleGoToEditor() {
    if (genProjectId) {
      const project = projects.find((p) => p.id === genProjectId)
      if (project) {
        dispatch(setCurrentProject(project))
        navigate(`/editor/${genProjectId}`)
      }
    }
    closeGenModal()
  }

  const isGenerating = ['starting', 'queued', 'in_progress'].includes(gen.status)
  const canCreate = projects.length < 3
  const genProject = genProjectId ? projects.find((p) => p.id === genProjectId) : null

  function isProjectGenerating(projectId) {
    return isGenerating && gen.projectId === projectId
  }

  function isProjectQueued(projectId) {
    return gen.status === 'queued' && gen.projectId === projectId
  }

  function isProjectDone(projectId) {
    return ['completed', 'completed_with_warnings'].includes(gen.status) && gen.projectId === projectId
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header />

      <main className="max-w-2xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>프로젝트</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{projects.length}/3</p>
          </div>
          {canCreate && !creating && !isGenerating && (
            <button onClick={() => setCreating(true)}
              className="re-btn-primary px-3 py-1.5 rounded-lg text-xs font-medium"
              style={{ background: 'var(--accent)', color: '#fff' }}>
              + 새 프로젝트
            </button>
          )}
        </div>

        {/* 새 프로젝트 폼 */}
        {creating && (
          <form onSubmit={handleCreate} className="rounded-lg p-4 mb-4" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
            <input type="text" placeholder="프로젝트 이름" value={newName} onChange={(e) => setNewName(e.target.value)}
              required autoFocus className="w-full px-3 py-2 rounded-lg text-sm outline-none mb-3"
              style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
            {createError && <p className="text-xs mb-2" style={{ color: '#f87171' }}>{createError}</p>}
            <div className="flex gap-2 justify-end">
              <button type="button"
                onClick={() => { setCreating(false); setCreateError(''); setNewName('') }}
                className="px-3 py-1.5 text-xs rounded-lg" style={{ color: 'var(--text-secondary)' }}>
                취소
              </button>
              <button type="submit" disabled={createLoading}
                className="re-btn-primary px-3 py-1.5 text-xs rounded-lg font-medium disabled:opacity-50"
                style={{ background: 'var(--accent)', color: '#fff' }}>
                {createLoading ? '생성 중...' : '만들기'}
              </button>
            </div>
          </form>
        )}

        {/* 프로젝트 목록 */}
        {isLoading ? (
          <p className="text-sm py-10 text-center" style={{ color: 'var(--text-secondary)' }}>불러오는 중...</p>
        ) : projects.length === 0 ? (
          <div className="rounded-lg p-10 text-center" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
            <p className="text-sm mb-1" style={{ color: 'var(--text-primary)' }}>아직 프로젝트가 없습니다</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>새 프로젝트를 만들어 세계를 창조하세요</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {projects.map((project) => {
              const generating = isProjectGenerating(project.id)
              const queued = isProjectQueued(project.id)
              const done = isProjectDone(project.id)
              return (
                <div key={project.id}
                  className={`re-card rounded-lg p-4 flex flex-col ${generating ? 'cursor-pointer' : ''}`}
                  style={{ background: 'var(--bg-secondary)', border: generating ? '1px solid var(--accent)' : '1px solid var(--border)' }}
                  onClick={generating ? () => { setGenProjectId(project.id); setGenModal('progress') } : undefined}>
                  <div className="flex-1 mb-3">
                    <h3 className="font-medium text-sm mb-0.5" style={{ color: 'var(--text-primary)' }}>{project.name}</h3>
                    {project.description && (
                      <p className="text-xs line-clamp-2 mb-1" style={{ color: 'var(--text-secondary)' }}>{project.description}</p>
                    )}
                    <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{relativeTime(project.updated_at)}</p>
                  </div>

                  {/* 대기열 상태 */}
                  {queued && (
                    <div className="mb-3 text-xs px-2 py-2 rounded-md" style={{ background: 'rgba(234,179,8,0.1)', border: '1px solid rgba(234,179,8,0.2)' }}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <span style={{ color: '#eab308' }}>대기열 {gen.queuePosition}번째</span>
                      </div>
                      <span style={{ color: 'var(--text-secondary)' }}>
                        예상 대기 약 {Math.ceil(gen.queueWaitSeconds / 60)}분
                      </span>
                    </div>
                  )}

                  {/* 생성 중 진행률 바 */}
                  {generating && !queued && (
                    <div className="mb-3">
                      <div className="flex justify-between text-xs mb-1">
                        <span style={{ color: 'var(--accent)' }}>{gen.message || '생성 중...'}</span>
                        <span style={{ color: 'var(--text-secondary)' }}>{gen.progress}%</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full" style={{ background: 'var(--border)' }}>
                        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${gen.progress}%`, background: 'var(--accent)' }} />
                      </div>
                    </div>
                  )}

                  {/* 생성 완료 알림 */}
                  {done && (
                    <div className="mb-3 text-xs px-2 py-1.5 rounded-md" style={{ background: 'rgba(34,197,94,0.1)', color: '#22c55e' }}>
                      생성 완료
                    </div>
                  )}

                  <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => handleEdit(project)}
                      disabled={generating}
                      className="re-btn-primary flex-1 py-1.5 text-xs rounded-md font-medium disabled:opacity-30"
                      style={{ background: 'var(--accent)', color: '#fff' }}>
                      게임 편집
                    </button>
                    <button onClick={() => openGenForm(project.id)}
                      disabled={isGenerating}
                      className="re-btn-secondary flex-1 py-1.5 text-xs rounded-md font-medium disabled:opacity-30"
                      style={{ background: 'var(--border)', color: 'var(--text-primary)' }}>
                      {generating ? '생성 중...' : 'AI 생성'}
                    </button>
                    <button onClick={() => setDeleteTarget(project)}
                      disabled={isGenerating}
                      className="py-1.5 px-2 text-xs rounded-md transition-colors hover:bg-red-500/10 disabled:opacity-30"
                      style={{ color: 'var(--text-secondary)' }}>
                      삭제
                    </button>
                  </div>
                </div>
              )
            })}

            {canCreate && !creating && !isGenerating && (
              <button onClick={() => setCreating(true)}
                className="rounded-lg p-4 flex items-center justify-center transition-colors hover:border-white/10"
                style={{ border: '1px dashed var(--border)', color: 'var(--text-secondary)', minHeight: 120 }}>
                <span className="text-xs">+ 새 프로젝트</span>
              </button>
            )}
          </div>
        )}
      </main>

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <Modal
          title="프로젝트 삭제"
          message={`"${deleteTarget.name}" 프로젝트를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
          errorMessage={deleteError}
          confirmLabel="삭제"
          onConfirm={handleDeleteConfirm}
          onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
          loading={deleteLoading}
        />
      )}

      {/* AI 생성 모달 */}
      {genModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="rounded-xl w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
            {/* 모달 헤더 */}
            <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
              <div>
                <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  {genModal === 'form' ? '세계 생성' : genModal === 'progress' ? '생성 중...' : '생성 완료'}
                </h3>
                {genProject && <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{genProject.name}</p>}
              </div>
              <button onClick={closeGenModal} className="w-7 h-7 flex items-center justify-center rounded transition-opacity hover:opacity-70"
                style={{ color: 'var(--text-secondary)' }}>
                ✕
              </button>
            </div>

            {/* 모달 콘텐츠 */}
            <div className="p-5">
              {genModal === 'form' && (
                <GenerationForm onSubmit={handleGenSubmit} isLoading={gen.status === 'starting'} />
              )}
              {genModal === 'progress' && (
                <GenerationProgress onDone={handleGenDone} />
              )}
              {genModal === 'result' && (
                <GenerationResult onRetry={handleGenRetry} onGoToEditor={handleGoToEditor} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
