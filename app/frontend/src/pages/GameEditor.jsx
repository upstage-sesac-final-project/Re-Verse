import { useState } from 'react'
import Header from '../components/layout/Header'
import ChatInterface from '../components/chat/ChatInterface'
import GamePreview from '../components/game/GamePreview'

export default function GameEditor() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [isCollapsed, setIsCollapsed] = useState(false)

  function handleGameUpdate() {
    setRefreshKey((prev) => prev + 1)
  }

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header />
      <div className="flex flex-1 overflow-hidden min-h-0">
        <ChatInterface
          onGameUpdate={handleGameUpdate}
          isCollapsed={isCollapsed}
          onToggleCollapse={() => setIsCollapsed((prev) => !prev)}
        />
        <GamePreview refreshKey={refreshKey} />
      </div>
    </div>
  )
}
