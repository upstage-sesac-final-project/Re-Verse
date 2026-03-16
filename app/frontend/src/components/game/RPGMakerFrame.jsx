export default function RPGMakerFrame({ refreshKey, gameId = 'game_001' }) {
  const scale = 0.9
  const width = 816
  const height = 624

  return (
    <div
      style={{
        width: width * scale,
        height: height * scale,
        overflow: 'hidden',
      }}
    >
      <iframe
        key={refreshKey}
        src={`/game/${gameId}/index.html`}
        title="RPG Maker MZ"
        allow="autoplay"
        width={width}
        height={height}
        style={{
          border: 'none',
          transformOrigin: '0 0',
          transform: `scale(${scale})`,
        }}
      />
    </div>
  )
}
