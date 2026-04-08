import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { fetchProjects, setCurrentProject } from '../store/gameSlice'
import { enterEditor, exitEditor, exitEditorBeacon } from '../services/editorApi'
import Header from '../components/layout/Header'
import ChatInterface from '../components/chat/ChatInterface'
import GamePreview from '../components/game/GamePreview'

export default function GameEditor() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const dispatch = useDispatch()
  const { projects, isLoading, currentProject } = useSelector((s) => s.game)

  const [refreshKey, setRefreshKey] = useState(0)
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [verified, setVerified] = useState(false)
  const sessionEnteredRef = useRef(false)

  // 편집 세션 종료 (beforeunload + cleanup 공용)
  const handleExit = useCallback(() => {
    if (sessionEnteredRef.current) {
      exitEditorBeacon(projectId)
      sessionEnteredRef.current = false
    }
  }, [projectId])

  useEffect(() => {
    setVerified(false)
    // 프로젝트 목록이 없으면 먼저 로드
    if (projects.length === 0 && !isLoading) {
      dispatch(fetchProjects())
      return
    }

    if (isLoading) return

    // 소유권 확인: 내 프로젝트 목록에 없으면 대시보드로 강제 이동
    const project = projects.find((p) => String(p.id) === projectId)
    if (!project) {
      navigate('/dashboard', { replace: true })
      return
    }

    dispatch(setCurrentProject(project))
    setVerified(true)

    // 편집 세션 시작
    enterEditor(projectId)
      .then(() => {
        sessionEnteredRef.current = true
      })
      .catch((err) => {
        console.error('편집 세션 시작 실패:', err)
        if (err.message?.includes('409')) {
          alert('이미 다른 탭에서 편집 중입니다.')
        }
        navigate('/dashboard', { replace: true })
      })

    // 페이지 이탈 시 세션 종료
    const onBeforeUnload = () => handleExit()
    window.addEventListener('beforeunload', onBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      // React cleanup (라우팅 이동 등)
      if (sessionEnteredRef.current) {
        exitEditor(projectId).catch(() => {})
        sessionEnteredRef.current = false
      }
    }
  }, [projectId, projects, isLoading, dispatch, navigate, handleExit])

  if (!verified) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ background: 'var(--bg-primary)' }}>
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          로딩 중...
        </span>
      </div>
    )
  }

  function handleGameUpdate() {
    setRefreshKey((prev) => prev + 1)
  }

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header />
      <div className="flex flex-1 overflow-hidden min-h-0">
        <ChatInterface
          projectId={projectId}
          onGameUpdate={handleGameUpdate}
          isCollapsed={isCollapsed}
          onToggleCollapse={() => setIsCollapsed((prev) => !prev)}
        />
        <GamePreview refreshKey={refreshKey} gameId={currentProject?.game_id} />
      </div>
    </div>
  )
}
