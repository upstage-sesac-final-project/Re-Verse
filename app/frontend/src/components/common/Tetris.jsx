import { useEffect, useRef, useState, useCallback } from 'react'

const COLS = 10
const ROWS = 20
const CELL = 24
const LINES_PER_LEVEL = 10
const SPEED = [500, 450, 400, 350, 300, 250, 200, 160, 130, 100, 80]
const HOLD_CELL = 16

const PIECES = [
  { shape: [[1,1,1,1]], color: '#00f0f0' },
  { shape: [[1,1],[1,1]], color: '#f0f000' },
  { shape: [[0,1,0],[1,1,1]], color: '#a000f0' },
  { shape: [[1,0,0],[1,1,1]], color: '#0000f0' },
  { shape: [[0,0,1],[1,1,1]], color: '#f0a000' },
  { shape: [[0,1,1],[1,1,0]], color: '#00f000' },
  { shape: [[1,1,0],[0,1,1]], color: '#f00000' },
]

function createBoard() { return Array.from({ length: ROWS }, () => Array(COLS).fill(null)) }

function randomPiece() {
  const p = PIECES[Math.floor(Math.random() * PIECES.length)]
  return { shape: p.shape.map(r => [...r]), color: p.color, x: Math.floor((COLS - p.shape[0].length) / 2), y: 0 }
}

function rotate(shape) {
  const rows = shape.length, cols = shape[0].length
  const out = Array.from({ length: cols }, () => Array(rows).fill(0))
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++)
      out[c][rows - 1 - r] = shape[r][c]
  return out
}

function collides(board, piece, dx = 0, dy = 0, newShape = null) {
  const s = newShape || piece.shape
  for (let r = 0; r < s.length; r++)
    for (let c = 0; c < s[r].length; c++) {
      if (!s[r][c]) continue
      const nx = piece.x + c + dx, ny = piece.y + r + dy
      if (nx < 0 || nx >= COLS || ny >= ROWS) return true
      if (ny >= 0 && board[ny][nx]) return true
    }
  return false
}

function merge(board, piece) {
  const b = board.map(r => [...r])
  piece.shape.forEach((row, r) =>
    row.forEach((v, c) => { if (v && piece.y + r >= 0) b[piece.y + r][piece.x + c] = piece.color })
  )
  return b
}

function clearLines(board) {
  const kept = board.filter(r => r.some(c => !c))
  const cleared = ROWS - kept.length
  const empty = Array.from({ length: cleared }, () => Array(COLS).fill(null))
  return { board: [...empty, ...kept], cleared }
}

function drawMiniPiece(ctx, piece, ox, oy, cellSize) {
  if (!piece) return
  const shape = PIECES.find(p => p.color === piece.color)?.shape || piece.shape
  shape.forEach((row, r) =>
    row.forEach((v, c) => {
      if (v) {
        ctx.fillStyle = piece.color
        ctx.fillRect(ox + c * cellSize + 1, oy + r * cellSize + 1, cellSize - 2, cellSize - 2)
      }
    })
  )
}

export default function Tetris() {
  const canvasRef = useRef(null)
  const holdCanvasRef = useRef(null)
  const nextCanvasRef = useRef(null)
  const boardRef = useRef(createBoard())
  const pieceRef = useRef(randomPiece())
  const nextRef = useRef(randomPiece())
  const holdRef = useRef(null)
  const canHoldRef = useRef(true)
  const [score, setScore] = useState(0)
  const [level, setLevel] = useState(0)
  const [lines, setLines] = useState(0)
  const [gameOver, setGameOver] = useState(false)
  const [started, setStarted] = useState(false)
  const tickRef = useRef(null)
  const gameOverRef = useRef(false)
  const linesRef = useRef(0)

  const draw = useCallback(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (!ctx) return
    const w = COLS * CELL, h = ROWS * CELL
    ctx.fillStyle = '#0a0a0a'
    ctx.fillRect(0, 0, w, h)
    ctx.strokeStyle = 'rgba(255,255,255,0.04)'
    ctx.lineWidth = 0.5
    for (let r = 0; r <= ROWS; r++) { ctx.beginPath(); ctx.moveTo(0, r * CELL); ctx.lineTo(w, r * CELL); ctx.stroke() }
    for (let c = 0; c <= COLS; c++) { ctx.beginPath(); ctx.moveTo(c * CELL, 0); ctx.lineTo(c * CELL, h); ctx.stroke() }

    boardRef.current.forEach((row, r) =>
      row.forEach((color, c) => {
        if (color) {
          ctx.fillStyle = color
          ctx.fillRect(c * CELL + 1, r * CELL + 1, CELL - 2, CELL - 2)
          ctx.fillStyle = 'rgba(255,255,255,0.15)'
          ctx.fillRect(c * CELL + 1, r * CELL + 1, CELL - 2, 3)
        }
      })
    )

    const p = pieceRef.current
    let ghostY = p.y
    while (!collides(boardRef.current, { ...p, y: ghostY + 1 }, 0, 0)) ghostY++
    if (ghostY !== p.y) {
      p.shape.forEach((row, r) =>
        row.forEach((v, c) => {
          if (v) {
            ctx.fillStyle = 'rgba(255,255,255,0.08)'
            ctx.fillRect((p.x + c) * CELL + 1, (ghostY + r) * CELL + 1, CELL - 2, CELL - 2)
          }
        })
      )
    }

    p.shape.forEach((row, r) =>
      row.forEach((v, c) => {
        if (v) {
          const px = (p.x + c) * CELL, py = (p.y + r) * CELL
          ctx.fillStyle = p.color
          ctx.fillRect(px + 1, py + 1, CELL - 2, CELL - 2)
          ctx.fillStyle = 'rgba(255,255,255,0.25)'
          ctx.fillRect(px + 1, py + 1, CELL - 2, 3)
        }
      })
    )

    const hCtx = holdCanvasRef.current?.getContext('2d')
    if (hCtx) { hCtx.fillStyle = '#0a0a0a'; hCtx.fillRect(0, 0, 80, 64); if (holdRef.current) drawMiniPiece(hCtx, holdRef.current, 8, 8, HOLD_CELL) }
    const nCtx = nextCanvasRef.current?.getContext('2d')
    if (nCtx) { nCtx.fillStyle = '#0a0a0a'; nCtx.fillRect(0, 0, 80, 64); drawMiniPiece(nCtx, nextRef.current, 8, 8, HOLD_CELL) }
  }, [])

  const tick = useCallback(() => {
    if (gameOverRef.current) return
    const board = boardRef.current, piece = pieceRef.current
    if (!collides(board, piece, 0, 1)) { piece.y++ }
    else {
      boardRef.current = merge(board, piece)
      const { board: newBoard, cleared } = clearLines(boardRef.current)
      boardRef.current = newBoard
      if (cleared > 0) {
        const lvl = Math.min(Math.floor(linesRef.current / LINES_PER_LEVEL), SPEED.length - 1)
        const pts = [0, 100, 300, 500, 800][cleared] * (lvl + 1)
        linesRef.current += cleared
        const newLvl = Math.min(Math.floor(linesRef.current / LINES_PER_LEVEL), SPEED.length - 1)
        setScore(s => s + pts); setLines(linesRef.current)
        if (newLvl !== lvl) { setLevel(newLvl); clearInterval(tickRef.current); tickRef.current = setInterval(tick, SPEED[newLvl]) }
      }
      const next = nextRef.current
      if (collides(boardRef.current, next)) { gameOverRef.current = true; setGameOver(true); return }
      pieceRef.current = { ...next, x: Math.floor((COLS - next.shape[0].length) / 2), y: 0 }
      nextRef.current = randomPiece(); canHoldRef.current = true
    }
    draw()
  }, [draw])

  const handleKey = useCallback((e) => {
    if (gameOverRef.current) return
    const piece = pieceRef.current, board = boardRef.current
    const key = e.key
    const code = e.code
    switch (true) {
      case key === 'ArrowLeft': if (!collides(board, piece, -1, 0)) piece.x--; break
      case key === 'ArrowRight': if (!collides(board, piece, 1, 0)) piece.x++; break
      case key === 'ArrowDown': if (!collides(board, piece, 0, 1)) piece.y++; break
      case key === 'ArrowUp': { const rotated = rotate(piece.shape); if (!collides(board, piece, 0, 0, rotated)) piece.shape = rotated; break }
      case key === ' ': while (!collides(board, piece, 0, 1)) piece.y++; break
      case code === 'KeyC' || key === 'Shift': {
        if (!canHoldRef.current) break
        const held = holdRef.current, orig = PIECES.find(p => p.color === piece.color)
        holdRef.current = { shape: orig.shape.map(r => [...r]), color: piece.color }
        if (held) pieceRef.current = { shape: held.shape.map(r => [...r]), color: held.color, x: Math.floor((COLS - held.shape[0].length) / 2), y: 0 }
        else { pieceRef.current = { ...nextRef.current, x: Math.floor((COLS - nextRef.current.shape[0].length) / 2), y: 0 }; nextRef.current = randomPiece() }
        canHoldRef.current = false; break
      }
      default: return
    }
    e.preventDefault(); draw()
  }, [draw])

  function start() {
    boardRef.current = createBoard(); pieceRef.current = randomPiece(); nextRef.current = randomPiece()
    holdRef.current = null; canHoldRef.current = true; linesRef.current = 0; gameOverRef.current = false
    setGameOver(false); setScore(0); setLevel(0); setLines(0); setStarted(true); draw()
  }

  useEffect(() => {
    if (!started) return
    tickRef.current = setInterval(tick, SPEED[0])
    window.addEventListener('keydown', handleKey)
    return () => { clearInterval(tickRef.current); window.removeEventListener('keydown', handleKey) }
  }, [started, tick, handleKey])

  useEffect(() => { if (gameOverRef.current && tickRef.current) clearInterval(tickRef.current) }, [gameOver])

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex gap-3 items-start">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold text-center" style={{ color: 'var(--text-secondary)' }}>HOLD</span>
          <canvas ref={holdCanvasRef} width={80} height={64} className="rounded" style={{ border: '1px solid var(--border)' }} />
        </div>
        <div className="relative" style={{ border: '2px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
          <canvas ref={canvasRef} width={COLS * CELL} height={ROWS * CELL} />
          {!started && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70">
              <p className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>TETRIS</p>
              <button onClick={start} className="px-4 py-1.5 text-xs rounded-lg font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>START</button>
            </div>
          )}
          {gameOver && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70">
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--accent)' }}>GAME OVER</p>
              <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>SCORE: {score}</p>
              <button onClick={start} className="px-4 py-1.5 text-xs rounded-lg font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>RETRY</button>
            </div>
          )}
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold text-center" style={{ color: 'var(--text-secondary)' }}>NEXT</span>
            <canvas ref={nextCanvasRef} width={80} height={64} className="rounded" style={{ border: '1px solid var(--border)' }} />
          </div>
          {started && (
            <div className="flex flex-col gap-1 text-[11px] tabular-nums" style={{ color: 'var(--text-secondary)' }}>
              <div>SCORE <span style={{ color: 'var(--text-primary)' }}>{score}</span></div>
              <div>LEVEL <span style={{ color: 'var(--accent)' }}>{level}</span></div>
              <div>LINES <span style={{ color: 'var(--text-primary)' }}>{lines}</span></div>
            </div>
          )}
        </div>
      </div>
      <div className="flex gap-3 text-[10px]" style={{ color: 'var(--text-secondary)' }}>
        <span>← → 이동</span><span>↑ 회전</span><span>↓ 낙하</span><span>SPACE 즉시</span><span>C 저장</span>
      </div>
    </div>
  )
}
