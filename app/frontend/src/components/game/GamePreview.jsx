import { useState, useEffect } from 'react'
import RPGMakerFrame from './RPGMakerFrame'
import GameDataViewer from './GameDataViewer'

const TABS = [
  { id: 'play', label: 'Play' },
  { id: 'map', label: 'Map Viewer' },
  { id: 'data', label: 'Game Data' },
]

// RPG Maker MZ 타일 ID → 색상 매핑
function getTileColor(tileId) {
  if (tileId === 0) return 'transparent'
  if (tileId >= 2816 && tileId < 4352) return '#3a5c3a' // A2: 지형 (풀/땅)
  if (tileId >= 4352 && tileId < 5888) return '#4a7c9a' // A3: 건물 지붕
  if (tileId >= 5888 && tileId < 8192) return '#2a4a6a' // A4: 벽/내부
  if (tileId >= 2048 && tileId < 2816) return '#5a9aaa' // A1: 물/애니메이션
  if (tileId >= 1536 && tileId < 2048) return '#8a6a3a' // 길
  return '#5a5a7a' // B~E: 오브젝트
}

function MapViewer({ gameId }) {
  const [mapData, setMapData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`/game/${gameId}/data/Map001.json`)
      .then((res) => {
        if (!res.ok) throw new Error('맵 데이터를 불러올 수 없습니다')
        return res.json()
      })
      .then(setMapData)
      .catch((e) => setError(e.message))
  }, [gameId])

  if (error) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-sm"
        style={{ color: 'var(--text-secondary)' }}
      >
        {error}
      </div>
    )
  }

  if (!mapData) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-sm"
        style={{ color: 'var(--text-secondary)' }}
      >
        로딩 중...
      </div>
    )
  }

  const { width, height, data } = mapData
  // data는 (레이어 수 × height × width) 1D 배열. 첫 번째 레이어만 사용
  const layer0 = data.slice(0, width * height)

  const cellSize = Math.min(Math.floor(600 / width), Math.floor(400 / height), 24)

  return (
    <div className="flex-1 overflow-auto flex flex-col items-center justify-center p-4">
      <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
        Map001 — {width} × {height} 타일
      </p>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${width}, ${cellSize}px)`,
          gap: '1px',
          background: 'var(--border)',
          border: '1px solid var(--border)',
        }}
      >
        {layer0.map((tileId, idx) => (
          <div
            key={idx}
            style={{
              width: cellSize,
              height: cellSize,
              background: getTileColor(tileId),
            }}
            title={`(${idx % width}, ${Math.floor(idx / width)}) id:${tileId}`}
          />
        ))}
      </div>
    </div>
  )
}


export default function GamePreview({ refreshKey, gameId = 'game_001' }) {
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

      {/* 탭 콘텐츠 */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        {activeTab === 'play' && <RPGMakerFrame refreshKey={refreshKey} gameId={gameId} />}
        {activeTab === 'map' && <MapViewer gameId={gameId} />}
        {activeTab === 'data' && <GameDataViewer gameId={gameId} />}
      </div>
    </div>
  )
}
