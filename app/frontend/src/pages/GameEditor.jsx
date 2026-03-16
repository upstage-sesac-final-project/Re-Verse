import { useState } from 'react'
import ChatInterface from '../components/chat/ChatInterface'
import RPGMakerFrame from '../components/game/RPGMakerFrame'

export default function GameEditor() {
  const [refreshKey, setRefreshKey] = useState(0)

  function handleGameUpdate() {
    setRefreshKey((prev) => prev + 1)
  }

  return (
    <div className="flex h-screen bg-gray-900">
      <div className="w-[400px] border-r border-gray-700 flex-shrink-0">
        <ChatInterface onGameUpdate={handleGameUpdate} />
      </div>
      <div className="flex-1 flex items-center justify-center">
        <RPGMakerFrame refreshKey={refreshKey} />
      </div>
    </div>
  )
}
