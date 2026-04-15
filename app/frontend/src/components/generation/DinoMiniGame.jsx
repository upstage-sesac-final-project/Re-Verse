import { useCallback, useEffect, useRef, useState } from 'react'

const WIDTH = 560
const HEIGHT = 170
const GROUND_Y = 132
const DINO_X = 56
const DINO_W = 22
const DINO_H = 24
const GRAVITY = 0.62
const JUMP_VELOCITY = -10.8

function createCutoutSprite(sourceImg, maxDimension = 512) {
  const srcW = sourceImg.naturalWidth || sourceImg.width
  const srcH = sourceImg.naturalHeight || sourceImg.height
  if (!srcW || !srcH) return sourceImg

  const scale = Math.min(1, maxDimension / Math.max(srcW, srcH))
  const w = Math.max(1, Math.round(srcW * scale))
  const h = Math.max(1, Math.round(srcH * scale))

  const workCanvas = document.createElement('canvas')
  workCanvas.width = w
  workCanvas.height = h
  const workCtx = workCanvas.getContext('2d')
  if (!workCtx) return sourceImg

  workCtx.imageSmoothingEnabled = false
  workCtx.drawImage(sourceImg, 0, 0, w, h)

  const imageData = workCtx.getImageData(0, 0, w, h)
  const data = imageData.data
  const total = w * h
  const marked = new Uint8Array(total)
  const queue = new Int32Array(total)
  let head = 0
  let tail = 0

  const isBgLikeAt = (idx) => {
    const o = idx * 4
    const r = data[o]
    const g = data[o + 1]
    const b = data[o + 2]
    const a = data[o + 3]
    if (a < 10) return true
    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    const grayish = max - min <= 10
    if (!grayish) return false
    const bright = r >= 235 && g >= 235 && b >= 232
    const checker = r >= 180 && r <= 210 && g >= 180 && g <= 210 && b >= 176 && b <= 208
    return bright || checker
  }

  const tryPush = (idx) => {
    if (idx < 0 || idx >= total) return
    if (marked[idx]) return
    if (!isBgLikeAt(idx)) return
    marked[idx] = 1
    queue[tail++] = idx
  }

  // 시작점: 이미지 테두리(체커 배경과 연결된 영역만 제거)
  for (let x = 0; x < w; x += 1) {
    tryPush(x)
    tryPush((h - 1) * w + x)
  }
  for (let y = 0; y < h; y += 1) {
    tryPush(y * w)
    tryPush(y * w + (w - 1))
  }

  while (head < tail) {
    const idx = queue[head++]
    const x = idx % w
    const y = (idx / w) | 0
    if (x > 0) tryPush(idx - 1)
    if (x < w - 1) tryPush(idx + 1)
    if (y > 0) tryPush(idx - w)
    if (y < h - 1) tryPush(idx + w)
  }

  // 배경으로 판정된 픽셀만 투명 처리
  for (let i = 0; i < total; i += 1) {
    if (marked[i]) data[i * 4 + 3] = 0
  }
  workCtx.putImageData(imageData, 0, 0)

  // 남은 픽셀 bbox 계산 후 잘라서 스프라이트 크기 최적화
  let minX = w
  let minY = h
  let maxX = -1
  let maxY = -1
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const a = data[(y * w + x) * 4 + 3]
      if (a > 0) {
        if (x < minX) minX = x
        if (y < minY) minY = y
        if (x > maxX) maxX = x
        if (y > maxY) maxY = y
      }
    }
  }

  if (maxX < minX || maxY < minY) return workCanvas

  const pad = 2
  const sx = Math.max(0, minX - pad)
  const sy = Math.max(0, minY - pad)
  const sw = Math.min(w - sx, maxX - minX + 1 + pad * 2)
  const sh = Math.min(h - sy, maxY - minY + 1 + pad * 2)

  const outCanvas = document.createElement('canvas')
  outCanvas.width = sw
  outCanvas.height = sh
  const outCtx = outCanvas.getContext('2d')
  if (!outCtx) return workCanvas
  outCtx.imageSmoothingEnabled = false
  outCtx.clearRect(0, 0, sw, sh)
  outCtx.drawImage(workCanvas, sx, sy, sw, sh, 0, 0, sw, sh)
  return outCanvas
}

export default function DinoMiniGame() {
  const canvasRef = useRef(null)
  const spriteRef = useRef(null)
  const spriteLoadedRef = useRef(false)
  const obstacleRef = useRef([])
  const dinoYRef = useRef(GROUND_Y - DINO_H)
  const dinoVyRef = useRef(0)
  const scoreRef = useRef(0)
  const speedRef = useRef(4.8)
  const spawnTimerRef = useRef(0)
  const frameRef = useRef(0)
  const gameOverRef = useRef(false)
  const bestRef = useRef(0)

  const [isGameOver, setIsGameOver] = useState(false)

  useEffect(() => {
    const img = new Image()
    img.src = '/assets/images/catsnailshark.png'
    img.onload = () => {
      try {
        spriteRef.current = createCutoutSprite(img)
        spriteLoadedRef.current = true
      } catch {
        spriteRef.current = img
        spriteLoadedRef.current = true
      }
    }
    img.onerror = () => {
      spriteRef.current = null
      spriteLoadedRef.current = false
    }
    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [])

  const jump = useCallback(() => {
    if (gameOverRef.current) return
    const onGround = dinoYRef.current >= GROUND_Y - DINO_H - 0.5
    if (onGround) {
      dinoVyRef.current = JUMP_VELOCITY
    }
  }, [])

  const restart = useCallback(() => {
    obstacleRef.current = []
    dinoYRef.current = GROUND_Y - DINO_H
    dinoVyRef.current = 0
    speedRef.current = 4.8
    spawnTimerRef.current = 0
    scoreRef.current = 0
    gameOverRef.current = false
    setIsGameOver(false)
  }, [])

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.code === 'Space' || e.code === 'ArrowUp') {
        e.preventDefault()
        if (gameOverRef.current) {
          restart()
        } else {
          jump()
        }
      }
      if (e.key.toLowerCase() === 'r' && gameOverRef.current) restart()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [jump, restart])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const checkCollision = (obs) => {
      const dinoRect = {
        x: DINO_X + 2,
        y: dinoYRef.current + 2,
        w: DINO_W - 4,
        h: DINO_H - 4,
      }
      const obstacleRect = { x: obs.x, y: obs.y, w: obs.w, h: obs.h }
      return (
        dinoRect.x < obstacleRect.x + obstacleRect.w &&
        dinoRect.x + dinoRect.w > obstacleRect.x &&
        dinoRect.y < obstacleRect.y + obstacleRect.h &&
        dinoRect.y + dinoRect.h > obstacleRect.y
      )
    }

    const draw = () => {
      frameRef.current += 1

      ctx.imageSmoothingEnabled = false
      ctx.clearRect(0, 0, WIDTH, HEIGHT)
      ctx.fillStyle = '#202125'
      ctx.fillRect(0, 0, WIDTH, HEIGHT)

      ctx.strokeStyle = '#8e8e93'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(0, GROUND_Y)
      ctx.lineTo(WIDTH, GROUND_Y)
      ctx.stroke()

      if (!gameOverRef.current) {
        dinoVyRef.current += GRAVITY
        dinoYRef.current += dinoVyRef.current
        if (dinoYRef.current > GROUND_Y - DINO_H) {
          dinoYRef.current = GROUND_Y - DINO_H
          dinoVyRef.current = 0
        }

        spawnTimerRef.current += 1
        const spawnEvery = Math.max(45, 88 - Math.floor(speedRef.current * 5))
        if (spawnTimerRef.current >= spawnEvery) {
          spawnTimerRef.current = 0
          const tall = Math.random() < 0.35
          obstacleRef.current.push({
            x: WIDTH + 8,
            y: tall ? GROUND_Y - 34 : GROUND_Y - 24,
            w: tall ? 14 : 12,
            h: tall ? 34 : 24,
          })
        }

        obstacleRef.current = obstacleRef.current
          .map((obs) => ({ ...obs, x: obs.x - speedRef.current }))
          .filter((obs) => obs.x + obs.w > -5)

        for (const obs of obstacleRef.current) {
          if (checkCollision(obs)) {
            gameOverRef.current = true
            setIsGameOver(true)
            bestRef.current = Math.max(bestRef.current, scoreRef.current)
            break
          }
        }

        if (!gameOverRef.current) {
          scoreRef.current += 1
          if (scoreRef.current % 220 === 0) speedRef.current += 0.18
        }
      }

      if (spriteLoadedRef.current && spriteRef.current) {
        // 픽셀아트 비율을 살리기 위해 가로/세로를 동일하게 맞춰 렌더링
        const spriteSize = 42
        const sx = DINO_X - 10
        const sy = dinoYRef.current - (spriteSize - DINO_H)
        ctx.drawImage(spriteRef.current, sx, sy, spriteSize, spriteSize)
      } else {
        // 이미지 로드 실패 시 폴백 캐릭터
        ctx.fillStyle = '#f2f2f7'
        ctx.fillRect(DINO_X, dinoYRef.current, DINO_W, DINO_H)
        ctx.fillRect(DINO_X + 16, dinoYRef.current + 5, 3, 3)
      }

      ctx.fillStyle = '#ff4d6d'
      for (const obs of obstacleRef.current) {
        ctx.fillRect(obs.x, obs.y, obs.w, obs.h)
      }

      ctx.fillStyle = '#b7b7bd'
      ctx.font = '12px Pretendard, sans-serif'
      ctx.fillText('Space/↑ 점프', 10, 18)
      ctx.fillText(`SCORE ${Math.floor(scoreRef.current / 4)}`, WIDTH - 102, 18)
      ctx.fillText(`BEST ${Math.floor(bestRef.current / 4)}`, WIDTH - 102, 34)

      if (gameOverRef.current) {
        ctx.fillStyle = 'rgba(0,0,0,0.55)'
        ctx.fillRect(0, 0, WIDTH, HEIGHT)
        ctx.fillStyle = '#f2f2f7'
        ctx.font = 'bold 16px Pretendard, sans-serif'
        ctx.fillText('GAME OVER', WIDTH / 2 - 52, HEIGHT / 2 - 4)
        ctx.font = '12px Pretendard, sans-serif'
        ctx.fillText('클릭 또는 Space로 다시 시작', WIDTH / 2 - 82, HEIGHT / 2 + 18)
      }

      frameRef.current = requestAnimationFrame(draw)
    }

    frameRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frameRef.current)
  }, [])

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
    >
      <p className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
        오래 기다리는 동안 잠깐: 공룡 점프 게임
      </p>
      <canvas
        ref={canvasRef}
        width={WIDTH}
        height={HEIGHT}
        onClick={() => (isGameOver ? restart() : jump())}
        className="w-full rounded-md cursor-pointer"
        style={{ maxWidth: '100%', aspectRatio: `${WIDTH} / ${HEIGHT}` }}
      />
    </div>
  )
}
