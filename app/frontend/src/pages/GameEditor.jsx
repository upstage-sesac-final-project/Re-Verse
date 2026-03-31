import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { fetchProjects, setCurrentProject } from '../store/gameSlice'
import Header from '../components/layout/Header'
import ChatInterface from '../components/chat/ChatInterface'
import GamePreview from '../components/game/GamePreview'

export default function GameEditor() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const dispatch = useDispatch()
  const { projects, isLoading } = useSelector((s) => s.game)

  const [refreshKey, setRefreshKey] = useState(0)
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [verified, setVerified] = useState(false)

  useEffect(() => {
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
  }, [projectId, projects, isLoading, dispatch, navigate])

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
        <GamePreview refreshKey={refreshKey} />
      </div>
    </div>
  )
}
