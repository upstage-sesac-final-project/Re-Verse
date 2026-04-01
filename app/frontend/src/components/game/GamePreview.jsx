import { useState } from 'react'
import RPGMakerFrame from './RPGMakerFrame'
import MapViewer from './MapViewer'
import GameDataViewer from './GameDataViewer'

const TABS = [
  { id: 'play', label: 'Play' },
  { id: 'map', label: 'Map Viewer' },
  { id: 'data', label: 'Game Data' },
]

export default function GamePreview({ refreshKey, gameId }) {
  const [activeTab, setActiveTab] = useState('play')

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full" style={{ background: 'var(--bg-primary)' }}>
      {/* 탭 바 */}
      <div
        className="h-10 flex items-center flex-shrink-0 px-2"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="px-4 h-full text-sm font-medium relative"
            style={{ color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)' }}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span
                className="absolute bottom-0 left-0 right-0 h-0.5"
                style={{ background: 'var(--accent)' }}
              />
            )}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 — keep all mounted to preserve state (iframe, map zoom, data cache) */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        <div className="flex-1 overflow-hidden flex flex-col min-h-0" style={{ display: activeTab === 'play' ? 'flex' : 'none' }}>
          <RPGMakerFrame refreshKey={refreshKey} gameId={gameId} />
        </div>
        <div className="flex-1 overflow-hidden flex flex-col min-h-0" style={{ display: activeTab === 'map' ? 'flex' : 'none' }}>
          <MapViewer gameId={gameId} />
        </div>
        <div className="flex-1 overflow-hidden flex flex-col min-h-0" style={{ display: activeTab === 'data' ? 'flex' : 'none' }}>
          <GameDataViewer gameId={gameId} />
        </div>
      </div>
    </div>
  )
}
