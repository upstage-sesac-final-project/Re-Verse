import { useRef, useState, useEffect } from 'react'

const GAME_WIDTH = 816
const GAME_HEIGHT = 624

export default function RPGMakerFrame({ refreshKey, gameId = 'game_001' }) {
  const containerRef = useRef(null)
  const [scale, setScale] = useState(1)

  useEffect(() => {
    function updateScale() {
      const el = containerRef.current
      if (!el) return
      const s = Math.min(el.clientWidth / GAME_WIDTH, el.clientHeight / GAME_HEIGHT)
      setScale(s)
    }

    updateScale()
    const observer = new ResizeObserver(updateScale)
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={containerRef} className="w-full h-full flex items-center justify-center">
      <div
        style={{
          width: GAME_WIDTH * scale,
          height: GAME_HEIGHT * scale,
          overflow: 'hidden',
        }}
      >
        <iframe
          key={refreshKey}
          src={`/game/${gameId}/index.html`}
          title="RPG Maker MZ"
          allow="autoplay"
          width={GAME_WIDTH}
          height={GAME_HEIGHT}
          style={{
            border: 'none',
            transformOrigin: '0 0',
            transform: `scale(${scale})`,
          }}
        />
      </div>
    </div>
  )
}
