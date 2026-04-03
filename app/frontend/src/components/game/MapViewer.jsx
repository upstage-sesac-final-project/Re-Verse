import { useState, useEffect, useRef, useCallback } from 'react'

// ── RPG Maker MZ 엔진과 동일한 오토타일 테이블 (rmmz_core.js 기준) ──
const FLOOR_AUTOTILE_TABLE = [
  [[2,4],[1,4],[2,3],[1,3]],[[2,0],[1,4],[2,3],[1,3]],[[2,4],[3,0],[2,3],[1,3]],[[2,0],[3,0],[2,3],[1,3]],
  [[2,4],[1,4],[2,3],[3,1]],[[2,0],[1,4],[2,3],[3,1]],[[2,4],[3,0],[2,3],[3,1]],[[2,0],[3,0],[2,3],[3,1]],
  [[2,4],[1,4],[2,1],[1,3]],[[2,0],[1,4],[2,1],[1,3]],[[2,4],[3,0],[2,1],[1,3]],[[2,0],[3,0],[2,1],[1,3]],
  [[2,4],[1,4],[2,1],[3,1]],[[2,0],[1,4],[2,1],[3,1]],[[2,4],[3,0],[2,1],[3,1]],[[2,0],[3,0],[2,1],[3,1]],
  [[0,4],[1,4],[0,3],[1,3]],[[0,4],[3,0],[0,3],[1,3]],[[0,4],[1,4],[0,3],[3,1]],[[0,4],[3,0],[0,3],[3,1]],
  [[2,2],[1,2],[2,3],[1,3]],[[2,2],[1,2],[2,3],[3,1]],[[2,2],[1,2],[2,1],[1,3]],[[2,2],[1,2],[2,1],[3,1]],
  [[2,4],[3,4],[2,3],[3,3]],[[2,4],[3,4],[2,1],[3,3]],[[2,0],[3,4],[2,3],[3,3]],[[2,0],[3,4],[2,1],[3,3]],
  [[2,4],[1,4],[2,5],[1,5]],[[2,0],[1,4],[2,5],[1,5]],[[2,4],[3,0],[2,5],[1,5]],[[2,0],[3,0],[2,5],[1,5]],
  [[0,4],[3,4],[0,3],[3,3]],[[2,2],[1,2],[2,5],[1,5]],[[0,2],[1,2],[0,3],[1,3]],[[0,2],[1,2],[0,3],[3,1]],
  [[2,2],[3,2],[2,3],[3,3]],[[2,2],[3,2],[2,1],[3,3]],[[2,4],[3,4],[2,5],[3,5]],[[2,0],[3,4],[2,5],[3,5]],
  [[0,4],[1,4],[0,5],[1,5]],[[0,4],[3,0],[0,5],[1,5]],[[0,2],[3,2],[0,3],[3,3]],[[0,2],[1,2],[0,5],[1,5]],
  [[0,4],[3,4],[0,5],[3,5]],[[2,2],[3,2],[2,5],[3,5]],[[0,2],[3,2],[0,5],[3,5]],[[0,0],[1,0],[0,1],[1,1]],
]
const WALL_AUTOTILE_TABLE = [
  [[2,2],[1,2],[2,1],[1,1]],[[0,2],[1,2],[0,1],[1,1]],[[2,0],[1,0],[2,1],[1,1]],[[0,0],[1,0],[0,1],[1,1]],
  [[2,2],[3,2],[2,1],[3,1]],[[0,2],[3,2],[0,1],[3,1]],[[2,0],[3,0],[2,1],[3,1]],[[0,0],[3,0],[0,1],[3,1]],
  [[2,2],[1,2],[2,3],[1,3]],[[0,2],[1,2],[0,3],[1,3]],[[2,0],[1,0],[2,3],[1,3]],[[0,0],[1,0],[0,3],[1,3]],
  [[2,2],[3,2],[2,3],[3,3]],[[0,2],[3,2],[0,3],[3,3]],[[2,0],[3,0],[2,3],[3,3]],[[0,0],[3,0],[0,3],[3,3]],
]
const WATERFALL_AUTOTILE_TABLE = [
  [[2,0],[1,0],[2,1],[1,1]],[[0,0],[1,0],[0,1],[1,1]],[[2,0],[3,0],[2,1],[3,1]],[[0,0],[3,0],[0,1],[3,1]],
]

// ── 오토타일 쿼터 피스 4개 조합 그리기 ────────────────────────
function drawAutoTile(ctx, img, bx, by, shape, table, cellSize, dx, dy) {
  const t = table[shape % table.length]
  if (!t) return
  const w1 = 24            // 쿼터 피스 크기 (px)
  const scale = cellSize / 48
  const dw = w1 * scale
  for (let i = 0; i < 4; i++) {
    const [qsx, qsy] = t[i]
    const srcX = (bx * 2 + qsx) * w1
    const srcY = (by * 2 + qsy) * w1
    const dstX = dx + (i % 2) * dw
    const dstY = dy + Math.floor(i / 2) * dw
    ctx.drawImage(img, srcX, srcY, w1, w1, dstX, dstY, dw, dw)
  }
}

// ── Canvas에 타일 1개 그리기 (엔진 공식 기준) ─────────────────
// images: [A1=0, A2=1, A3=2, A4=3, A5=4, B=5, C=6, D=7, E=8]
function drawTile(ctx, tileId, dx, dy, cellSize, images) {
  if (tileId === 0) return
  const TS = 48

  // 오토타일 공통: 전역 kind & shape (A1 기준)
  const globalKind = Math.floor((tileId - 2048) / 48)
  const shape      = (tileId - 2048) % 48
  const tx = globalKind % 8
  const ty = Math.floor(globalKind / 8)

  // ── A1 애니메이션 타일 (2048~2815) ──────────────────────────
  if (tileId >= 2048 && tileId < 2816) {
    const img = images[0]
    if (!img) return
    const kind = globalKind  // 0~15
    let bx, by, table
    if (kind === 0)      { bx = 0; by = 0; table = FLOOR_AUTOTILE_TABLE }
    else if (kind === 1) { bx = 0; by = 3; table = FLOOR_AUTOTILE_TABLE }
    else if (kind === 2) { bx = 6; by = 0; table = FLOOR_AUTOTILE_TABLE }
    else if (kind === 3) { bx = 6; by = 3; table = FLOOR_AUTOTILE_TABLE }
    else {
      bx = Math.floor(tx / 4) * 8
      by = ty * 6 + (Math.floor(tx / 2) % 2) * 3
      if (kind % 2 === 0) { table = FLOOR_AUTOTILE_TABLE }
      else { bx += 6; table = WATERFALL_AUTOTILE_TABLE }
    }
    drawAutoTile(ctx, img, bx, by, shape, table, cellSize, dx, dy)
    return
  }

  // ── A2 지면 오토타일 (2816~4351) ────────────────────────────
  if (tileId >= 2816 && tileId < 4352) {
    const img = images[1]
    if (!img) return
    const bx = tx * 2
    const by = (ty - 2) * 3
    drawAutoTile(ctx, img, bx, by, shape, FLOOR_AUTOTILE_TABLE, cellSize, dx, dy)
    return
  }

  // ── A3 지붕 오토타일 (4352~5887) ────────────────────────────
  if (tileId >= 4352 && tileId < 5888) {
    const img = images[2]
    if (!img) return
    const bx = tx * 2
    const by = (ty - 6) * 2
    drawAutoTile(ctx, img, bx, by, shape, WALL_AUTOTILE_TABLE, cellSize, dx, dy)
    return
  }

  // ── A4 벽 오토타일 (5888~8191) ──────────────────────────────
  if (tileId >= 5888 && tileId < 8192) {
    const img = images[3]
    if (!img) return
    const bx = tx * 2
    const by = Math.floor((ty - 10) * 2.5 + (ty % 2 === 1 ? 0.5 : 0))
    const table = ty % 2 === 1 ? WALL_AUTOTILE_TABLE : FLOOR_AUTOTILE_TABLE
    drawAutoTile(ctx, img, bx, by, shape, table, cellSize, dx, dy)
    return
  }

  // ── A5 일반 타일 (1536~2047) ────────────────────────────────
  if (tileId >= 1536 && tileId < 2048) {
    const img = images[4]
    if (!img) return
    const sx = ((Math.floor(tileId / 128) % 2) * 8 + (tileId % 8)) * TS
    const sy = (Math.floor((tileId % 256) / 8) % 16) * TS
    ctx.drawImage(img, sx, sy, TS, TS, dx, dy, cellSize, cellSize)
    return
  }

  // ── B~E 일반 타일 (0~1023) ──────────────────────────────────
  if (tileId >= 0 && tileId < 1024) {
    const setNumber = 5 + Math.floor(tileId / 256)
    const img = images[setNumber]
    if (!img) return
    const sx = ((Math.floor(tileId / 128) % 2) * 8 + (tileId % 8)) * TS
    const sy = (Math.floor((tileId % 256) / 8) % 16) * TS
    ctx.drawImage(img, sx, sy, TS, TS, dx, dy, cellSize, cellSize)
  }
}

// ── 이벤트 페이지 디코딩 헬퍼 ────────────────────────────────
const TRIGGER_LABEL = ['버튼', '플레이어 접촉', '이벤트 접촉', '자동실행', '병렬처리']
const MOVE_TYPE_LABEL = ['고정', '랜덤', '접근', '커스텀']
const PRIORITY_LABEL = ['하층', '캐릭터와 동층', '상층']

const CMD_LABEL = {
  101: (p) => `💬 메시지: "${p[4] || ''}"`,
  401: (p) => `   "${p[0]}"`,
  102: (p) => `❓ 선택지: [${p[0]?.join(' / ')}]`,
  111: () => '┌ 조건 분기',
  411: () => '├ 아닐 때',
  412: () => '└ 분기 끝',
  112: () => '↩ 반복',
  113: () => '⛔ 반복 중단',
  115: () => '⏹ 이벤트 종료',
  117: (p) => `📋 공통 이벤트 #${p[0]}`,
  121: (p) => `🔘 스위치 #${p[0]}~#${p[1]} ${p[2] === 0 ? 'ON' : 'OFF'}`,
  122: (p) => `🔢 변수 #${p[0]} 조작`,
  123: (p) => `🔀 셀프스위치 ${p[0]} ${p[1] === 0 ? 'ON' : 'OFF'}`,
  201: (p) => `🚀 장소이동 → 맵#${p[1]} (${p[2]},${p[3]})`,
  205: () => '🚶 이동 루트 설정',
  216: (p) => `👁 투명화 ${p[0] ? 'ON' : 'OFF'}`,
  220: () => '⬛ 화면 페이드 아웃',
  221: () => '⬜ 화면 페이드 인',
  222: () => '🎨 화면 색조 변경',
  223: () => '⚡ 화면 플래시',
  224: () => '📳 화면 진동',
  230: (p) => `⏱ 대기 ${p[0]}프레임`,
  231: () => '🖼 픽처 표시',
  235: () => '🗑 픽처 지우기',
  241: (p) => `🎵 BGM: ${p[0]?.name ?? ''}`,
  249: (p) => `🎶 ME: ${p[0]?.name ?? ''}`,
  250: (p) => `🔔 SE: ${p[0]?.name ?? ''}`,
  301: (p) => `⚔️ 전투 처리 (트룹#${p[1]})`,
  601: () => '├ 승리 시',
  602: () => '├ 도망 시',
  603: () => '├ 패배 시',
  604: () => '└ 전투 끝',
  302: () => '🛒 상점 처리',
  311: () => '❤️ HP 변경',
  312: () => '💧 MP 변경',
  342: () => '✨ TP 변경',
  321: () => '🎭 직업 변경',
  322: () => '📚 스킬 증감',
  323: () => '🗡 장비 변경',
  351: () => '📜 메뉴 화면',
  352: () => '💾 세이브 화면',
  353: () => '💀 게임 오버',
  354: () => '🏠 타이틀로',
  355: (p) => `⚙️ 스크립트: ${String(p[0]).slice(0, 30)}`,
  356: (p) => `🔌 플러그인: ${String(p[0]).slice(0, 30)}`,
}

function decodeCommand(cmd) {
  if (cmd.code === 0) return null
  const fn = CMD_LABEL[cmd.code]
  if (fn) {
    try { return fn(cmd.parameters) } catch { return `[${cmd.code}]` }
  }
  return `[cmd:${cmd.code}]`
}

function getConditionTags(cond) {
  const tags = []
  if (cond.switch1Valid) tags.push(`SW#${cond.switch1Id} ON`)
  if (cond.switch2Valid) tags.push(`SW#${cond.switch2Id} ON`)
  if (cond.variableValid) tags.push(`변수#${cond.variableId}≥${cond.variableValue}`)
  if (cond.selfSwitchValid) tags.push(`셀프SW ${cond.selfSwitchCh} ON`)
  if (cond.actorValid) tags.push(`액터#${cond.actorId}`)
  if (cond.itemValid) tags.push(`아이템#${cond.itemId}`)
  return tags
}

// ── 이벤트 페이지 상세 컴포넌트 ──────────────────────────────
function PageDetail({ page, index }) {
  const [open, setOpen] = useState(false)
  const conds = getConditionTags(page.conditions ?? {})
  const cmds = (page.list ?? []).map(decodeCommand).filter(Boolean)

  return (
    <div className="rounded mb-1.5" style={{ border: '1px solid var(--border)', background: 'var(--bg-primary)' }}>
      {/* 페이지 헤더 */}
      <button
        className="w-full flex items-center justify-between px-2 py-1.5 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Page {index + 1}
          {page.image?.characterName
            ? <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}> · {page.image.characterName}</span>
            : null}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{open ? '▲' : '▼'}</span>
      </button>

      {/* 페이지 요약 (항상 표시) */}
      <div className="px-2 pb-1.5 flex flex-wrap gap-1">
        <Tag color="#7c5cff">{TRIGGER_LABEL[page.trigger] ?? page.trigger}</Tag>
        <Tag color="#4caf82">{MOVE_TYPE_LABEL[page.moveType] ?? page.moveType}</Tag>
        <Tag color="#6b6b8a">{PRIORITY_LABEL[page.priorityType] ?? page.priorityType}</Tag>
        {conds.map((c, i) => <Tag key={i} color="#e0a020">{c}</Tag>)}
      </div>

      {/* 명령어 목록 (펼쳤을 때) */}
      {open && cmds.length > 0 && (
        <div
          className="px-2 pb-2 pt-1 space-y-0.5"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          {cmds.map((text, i) => (
            <div key={i} className="text-xs" style={{ color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
              {text}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Tag({ color, children }) {
  return (
    <span
      className="px-1 py-0.5 rounded text-xs"
      style={{ background: color + '22', color, border: `1px solid ${color}55`, lineHeight: 1 }}
    >
      {children}
    </span>
  )
}

// ── 이벤트 종류 판별 (커맨드 코드 기반) ──────────────────────
function getEventType(event) {
  for (const page of (event.pages ?? [])) {
    for (const cmd of (page.list ?? [])) {
      if (cmd.code === 201) return 'warp'
      if (cmd.code === 301) return 'battle'
      if (cmd.code === 101 || cmd.code === 102 || cmd.code === 302) return 'npc'
    }
  }
  return 'other'
}

const EVENT_COLOR = { warp: '#5b8dee', npc: '#4caf82', battle: '#e05252', other: '#f0a500' }
function getEventColor(event) {
  return EVENT_COLOR[getEventType(event)]
}

// ── 이미지 로드 헬퍼 ──────────────────────────────────────────
function loadImage(src) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = src
  })
}

const ZOOM_MIN = 0.5
const ZOOM_MAX = 3.0
const ZOOM_STEP = 0.25
const BASE_CELL = 48

export default function MapViewer({ gameId, refreshKey }) {
  const [mapList, setMapList]       = useState([])
  const [selectedMapId, setSelectedMapId] = useState(1)
  const [mapData, setMapData]       = useState(null)
  const [tileImages, setTileImages] = useState([]) // index = tilesetNames 배열 위치
  const [hoveredEvent, setHoveredEvent] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [isLoading, setIsLoading]   = useState(false)
  const [error, setError]           = useState(null)
  const [zoom, setZoom]             = useState(0.5)
  const canvasRef = useRef(null)

  // Re-fetch map list when game data is updated by the AI
  useEffect(() => {
    if (refreshKey === 0) return  // skip initial mount (handled by the main effect)
    fetch(`/game/${gameId}/data/MapInfos.json`)
      .then((r) => r.json())
      .then((data) => {
        const list = data.filter(Boolean).sort((a, b) => a.order - b.order)
        setMapList(list)
      })
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  // MapInfos.json 로드
  useEffect(() => {
    fetch(`/game/${gameId}/data/MapInfos.json`)
      .then((r) => r.json())
      .then((data) => {
        const list = data.filter(Boolean).sort((a, b) => a.order - b.order)
        setMapList(list)
        if (list.length > 0) setSelectedMapId(list[0].id)
      })
      .catch(() => setError('맵 목록을 불러올 수 없습니다'))
  }, [gameId])

  // 선택된 맵 데이터 + 타일셋 이미지 로드
  useEffect(() => {
    if (!selectedMapId) return
    setIsLoading(true)
    setMapData(null)
    setTileImages([])
    setSelectedEvent(null)
    setHoveredEvent(null)
    setError(null)

    const mapFilename = `Map${String(selectedMapId).padStart(3, '0')}.json`

    Promise.all([
      fetch(`/game/${gameId}/data/${mapFilename}`).then((r) => r.json()),
      fetch(`/game/${gameId}/data/Tilesets.json`).then((r) => r.json()),
    ])
      .then(async ([map, tilesets]) => {
        setMapData(map)
        const ts = tilesets[map.tilesetId]
        if (!ts) return

        // tilesetNames: [A1, A2, A3, A4, A5, B, C, D, E]
        const imgs = await Promise.all(
          ts.tilesetNames.map((name) =>
            name ? loadImage(`/game/${gameId}/img/tilesets/${name}.png`) : Promise.resolve(null)
          )
        )
        setTileImages(imgs)
      })
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
  }, [gameId, selectedMapId, refreshKey])

  // Canvas 렌더링
  const cellSize = Math.max(4, Math.round(BASE_CELL * zoom))

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || !mapData) return
    const { width, height, data } = mapData

    canvas.width  = width  * cellSize
    canvas.height = height * cellSize

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 배경
    ctx.fillStyle = '#1a1a2a'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // 레이어 0~3: 일반 타일 렌더링
    for (let layer = 0; layer < 4; layer++) {
      const layerData = data.slice(layer * width * height, (layer + 1) * width * height)
      layerData.forEach((tileId, idx) => {
        if (tileId === 0) return
        const tx = idx % width
        const ty = Math.floor(idx / width)
        drawTile(ctx, tileId, tx * cellSize, ty * cellSize, cellSize, tileImages)
      })
    }

    // 레이어 4: 그림자 레이어 (비트 플래그 0~15, 반투명 검정)
    const shadowData = data.slice(4 * width * height, 5 * width * height)
    ctx.fillStyle = 'rgba(0,0,0,0.5)'
    shadowData.forEach((flags, idx) => {
      if (flags === 0) return
      const tx = idx % width
      const ty = Math.floor(idx / width)
      const hx = tx * cellSize, hy = ty * cellSize
      const hw = cellSize / 2
      if (flags & 1) ctx.fillRect(hx,      hy,      hw, hw) // 좌상
      if (flags & 2) ctx.fillRect(hx + hw, hy,      hw, hw) // 우상
      if (flags & 4) ctx.fillRect(hx,      hy + hw, hw, hw) // 좌하
      if (flags & 8) ctx.fillRect(hx + hw, hy + hw, hw, hw) // 우하
    })

    // 레이어 5: 리전 ID (렌더링 생략)
  }, [mapData, tileImages, cellSize])

  useEffect(() => {
    drawCanvas()
  }, [drawCanvas])

  const events = mapData ? (mapData.events ?? []).filter(Boolean) : []

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* ── 헤더 ── */}
      <div
        className="flex items-center gap-3 px-3 py-2 flex-shrink-0 flex-wrap"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}
      >
        <label className="text-xs flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>맵 선택</label>
        <select
          value={selectedMapId}
          onChange={(e) => setSelectedMapId(Number(e.target.value))}
          className="flex-1 px-2 py-1 rounded text-xs"
          style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
        >
          {mapList.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} (Map{String(m.id).padStart(3, '0')})
            </option>
          ))}
        </select>
        {mapData && (
          <span className="text-xs flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
            {mapData.width} × {mapData.height} · 이벤트 {events.length}개
          </span>
        )}

        {/* 줌 컨트롤 */}
        <div className="flex items-center gap-1.5 ml-auto flex-shrink-0">
          <button
            onClick={() => setZoom((z) => Math.max(ZOOM_MIN, Math.round((z - ZOOM_STEP) * 100) / 100))}
            disabled={zoom <= ZOOM_MIN}
            className="w-6 h-6 rounded flex items-center justify-center text-sm disabled:opacity-30"
            style={{ background: 'var(--border)', color: 'var(--text-primary)' }}
          >−</button>
          <input
            type="range" min={ZOOM_MIN} max={ZOOM_MAX} step={ZOOM_STEP} value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="w-24"
            style={{ accentColor: 'var(--accent)' }}
          />
          <button
            onClick={() => setZoom((z) => Math.min(ZOOM_MAX, Math.round((z + ZOOM_STEP) * 100) / 100))}
            disabled={zoom >= ZOOM_MAX}
            className="w-6 h-6 rounded flex items-center justify-center text-sm disabled:opacity-30"
            style={{ background: 'var(--border)', color: 'var(--text-primary)' }}
          >+</button>
          <span className="text-xs w-10 text-right" style={{ color: 'var(--text-secondary)' }}>
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom(1.0)}
            className="text-xs px-1.5 py-0.5 rounded"
            style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
          >1:1</button>
        </div>
      </div>

      {/* ── 본문 ── */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        <div className="flex-1 overflow-auto flex flex-col items-center justify-center p-4">
          {error   && <p className="text-sm" style={{ color: '#e05555' }}>{error}</p>}
          {isLoading && <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>로딩 중...</p>}

          {mapData && !isLoading && (
            <div style={{ position: 'relative', display: 'inline-block' }}>
              {/* Canvas 타일 렌더링 */}
              <canvas
                ref={canvasRef}
                style={{ display: 'block', imageRendering: 'pixelated' }}
              />

              {/* 이벤트 오버레이 */}
              {events.map((ev) => {
                const color = getEventColor(ev)
                const isSelected = selectedEvent?.id === ev.id
                return (
                  <div
                    key={ev.id}
                    onClick={() => setSelectedEvent(isSelected ? null : ev)}
                    onMouseEnter={() => setHoveredEvent(ev)}
                    onMouseLeave={() => setHoveredEvent(null)}
                    style={{
                      position: 'absolute',
                      left: ev.x * cellSize,
                      top: ev.y * cellSize,
                      width: cellSize,
                      height: cellSize,
                      background: color + (isSelected ? '55' : '33'),
                      border: `2px solid ${color}`,
                      borderRadius: '3px',
                      cursor: 'pointer',
                      boxShadow: isSelected ? `0 0 8px ${color}` : 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxSizing: 'border-box',
                    }}
                  >
                    {cellSize >= 16 && (
                      <span style={{ fontSize: Math.max(8, cellSize * 0.4), lineHeight: 1, color }}>
                        {getEventType(ev) === 'warp' ? '⬡' : '●'}
                      </span>
                    )}
                  </div>
                )
              })}

              {/* 호버 tooltip */}
              {hoveredEvent && !selectedEvent && (
                <div
                  style={{
                    position: 'absolute',
                    left: hoveredEvent.x * cellSize,
                    top: Math.max(4, hoveredEvent.y * cellSize - 28),
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    borderRadius: '4px',
                    padding: '2px 8px',
                    fontSize: '11px',
                    color: 'var(--text-primary)',
                    whiteSpace: 'nowrap',
                    pointerEvents: 'none',
                    zIndex: 10,
                  }}
                >
                  {hoveredEvent.name}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 이벤트 사이드 패널 */}
        {selectedEvent && (
          <div
            className="w-64 flex-shrink-0 overflow-y-auto p-3"
            style={{ borderLeft: '1px solid var(--border)', background: 'var(--bg-secondary)' }}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>이벤트 정보</span>
              <button onClick={() => setSelectedEvent(null)} aria-label="이벤트 패널 닫기" className="text-xs hover:opacity-70" style={{ color: 'var(--text-secondary)' }}>✕</button>
            </div>
            <div className="space-y-2 text-xs">
              <Row label="이름" value={selectedEvent.name} />
              <Row label="ID"   value={`#${selectedEvent.id}`} />
              <Row label="좌표" value={`(${selectedEvent.x}, ${selectedEvent.y})`} />
              <Row label="페이지" value={`${selectedEvent.pages?.length ?? 0}개`} />
              {selectedEvent.note && <Row label="메모" value={selectedEvent.note} />}
            </div>
            {selectedEvent.pages?.length > 0 && (
              <div className="mt-3">
                <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
                  페이지 ({selectedEvent.pages.length}개)
                </p>
                {selectedEvent.pages.map((page, i) => (
                  <PageDetail key={i} page={page} index={i} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 범례 */}
      <div
        className="flex items-center gap-4 px-3 py-1.5 flex-shrink-0 text-xs"
        style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
      >
        <Legend color="#5b8dee" label="워프(201)" />
        <Legend color="#4caf82" label="NPC(101·102·302)" />
        <Legend color="#e05252" label="전투(301)" />
        <Legend color="#f0a500" label="기타 이벤트" />
        <span style={{ marginLeft: 'auto' }}>클릭 시 상세 보기</span>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex gap-2">
      <span className="w-14 flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  )
}

function Legend({ color, label }) {
  return (
    <div className="flex items-center gap-1">
      <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
      <span>{label}</span>
    </div>
  )
}
