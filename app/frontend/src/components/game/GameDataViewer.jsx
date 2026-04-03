import { useState, useEffect } from 'react'

// ── RPG Maker MZ 필드 설명 사전 ────────────────────────────────
const FIELD_DESC = {
  'Actors.json': {
    id: '고유 ID',
    name: '캐릭터 이름',
    nickname: '캐릭터 별명 (칭호)',
    classId: '직업 ID (Classes.json 참조)',
    initialLevel: '초기 레벨',
    maxLevel: '최대 레벨',
    characterName: '맵 스프라이트 파일명 (img/characters/)',
    characterIndex: '스프라이트 시트 내 인덱스 (0~7)',
    faceName: '얼굴 이미지 파일명 (img/faces/)',
    faceIndex: '얼굴 시트 내 인덱스 (0~7)',
    battlerName: '전투 스프라이트 파일명 (img/sv_actors/)',
    equips: '초기 장비 [무기ID, 방패ID, 머리ID, 몸ID, 장신구ID]',
    traits: '특성 배열 [{code, dataId, value}]',
    note: '메모 (플러그인 태그)',
  },
  'Enemies.json': {
    id: '고유 ID',
    name: '적 이름',
    battlerName: '전투 이미지 파일명 (img/enemies/)',
    battlerHue: '이미지 색조 (0~360)',
    params: '능력치 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]',
    exp: '처치 시 획득 경험치',
    gold: '처치 시 획득 골드',
    dropItems: '드롭 아이템 [{kind, dataId, denominator}]',
    actions: '행동 패턴 [{skillId, conditionType, rating}]',
    traits: '특성 배열',
    note: '메모',
  },
  'Skills.json': {
    id: '고유 ID',
    name: '스킬명',
    description: '스킬 설명',
    stypeId: '스킬 유형 (1=마법, 2=필살기)',
    mpCost: 'MP 소비량',
    tpCost: 'TP 소비량',
    scope: '효과 범위 (1=적1체, 2=적전체, 7=아군1체)',
    occasion: '사용 가능 상황 (0=항상, 1=전투만)',
    speed: '속도 보정값',
    successRate: '성공률 (%)',
    damage: '데미지 설정 {type, elementId, formula}',
    effects: '효과 배열 [{code, dataId, value1, value2}]',
    note: '메모',
  },
  'Items.json': {
    id: '고유 ID',
    name: '아이템명',
    description: '아이템 설명',
    price: '상점 가격 (0=판매불가)',
    itypeId: '아이템 유형 (1=일반, 2=핵심)',
    consumable: '소모품 여부',
    scope: '효과 범위',
    occasion: '사용 가능 상황 (0=항상, 2=메뉴만)',
    effects: '효과 배열 [{code, dataId, value1, value2}]',
    note: '메모',
  },
  'Weapons.json': {
    id: '고유 ID',
    name: '무기명',
    wtypeId: '무기 유형 (1=단검, 2=검, 3=도끼)',
    params: '능력치 보정 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]',
    traits: '특성 배열',
    animationId: '공격 애니메이션 ID',
    price: '상점 가격',
    note: '메모',
  },
  'Armors.json': {
    id: '고유 ID',
    name: '방어구명',
    atypeId: '방어구 유형',
    etypeId: '장비 유형 (2=방패, 3=머리, 4=몸, 5=장신구)',
    params: '능력치 보정 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]',
    traits: '특성 배열',
    price: '상점 가격',
    note: '메모',
  },
  'System.json': {
    gameTitle: '게임 제목',
    versionId: '프로젝트 버전 ID',
    locale: '언어 설정 (ko_KR, en_US)',
    partyMembers: '초기 파티 멤버 [actorId, ...]',
    currency: '화폐 단위',
    optSideView: '사이드뷰 전투 여부',
    optDisplayTp: 'TP 표시 여부',
    battleBgm: '전투 BGM 설정',
    tileSize: '타일 크기 (px, 기본 48)',
    startMapId: '시작 맵 ID',
    startX: '시작 X 좌표',
    startY: '시작 Y 좌표',
  },
}

const PARAMS_LABEL = ['MHP', 'MMP', 'ATK', 'DEF', 'MAT', 'MDF', 'AGI', 'LUK']

const DATA_FILES = [
  'Enemies.json',
  'Skills.json',
  'Items.json',
  'Actors.json',
  'Weapons.json',
  'Armors.json',
  'System.json',
]

// ── 값 렌더링 ──────────────────────────────────────────────────
function ValueCell({ field, value }) {
  if (value === null || value === undefined) {
    return <span style={{ color: 'var(--text-secondary)' }}>—</span>
  }
  // params 배열 (능력치)
  if (field === 'params' && Array.isArray(value)) {
    return (
      <div className="flex flex-wrap gap-1">
        {value.slice(0, 8).map((v, i) => (
          <span
            key={i}
            className="px-1.5 py-0.5 rounded text-xs"
            style={{ background: 'var(--border)', color: 'var(--text-primary)' }}
            title={PARAMS_LABEL[i]}
          >
            {PARAMS_LABEL[i]}:{v}
          </span>
        ))}
      </div>
    )
  }
  if (typeof value === 'boolean') {
    return (
      <span style={{ color: value ? '#4caf82' : '#e05555' }}>{value ? 'true' : 'false'}</span>
    )
  }
  if (Array.isArray(value)) {
    return (
      <span style={{ color: 'var(--text-secondary)' }}>
        [{value.length}개]
      </span>
    )
  }
  if (typeof value === 'object') {
    return <span style={{ color: 'var(--text-secondary)' }}>{'{...}'}</span>
  }
  return <span style={{ color: 'var(--text-primary)' }}>{String(value)}</span>
}

// ── 아이템 카드 (배열형 파일) ───────────────────────────────────
function ItemCard({ item, filename }) {
  const [expanded, setExpanded] = useState(false)
  const fieldDescs = FIELD_DESC[filename] ?? {}

  const topFields = ['id', 'name', 'description', 'params', 'exp', 'gold', 'mpCost', 'tpCost', 'price']
  const displayFields = Object.keys(item).filter((k) => k !== 'note' && k !== 'meta')

  return (
    <div
      className="rounded-lg mb-2"
      style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)' }}
    >
      {/* 헤더 */}
      <button
        className="w-full flex items-center justify-between px-3 py-2 text-left"
        onClick={() => setExpanded((p) => !p)}
      >
        <div className="flex items-center gap-2">
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            #{item.id}
          </span>
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {item.name || '(이름 없음)'}
          </span>
          {item.description && (
            <span className="text-xs truncate max-w-[200px]" style={{ color: 'var(--text-secondary)' }}>
              {item.description}
            </span>
          )}
        </div>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {/* 상세 */}
      {expanded && (
        <div
          className="px-3 pb-3 pt-1"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          {/* 주요 필드 먼저 */}
          {topFields
            .filter((f) => f in item && f !== 'id' && f !== 'name' && f !== 'description')
            .map((field) => (
              <FieldRow key={field} field={field} value={item[field]} desc={fieldDescs[field]} />
            ))}
          {/* 나머지 필드 */}
          {displayFields
            .filter((f) => !topFields.includes(f))
            .map((field) => (
              <FieldRow key={field} field={field} value={item[field]} desc={fieldDescs[field]} />
            ))}
        </div>
      )}
    </div>
  )
}

function FieldRow({ field, value, desc }) {
  return (
    <div className="flex items-start gap-2 py-1 text-xs" style={{ borderBottom: '1px solid var(--border)' }}>
      <div className="w-32 flex-shrink-0 flex items-center gap-1">
        <span style={{ color: 'var(--accent)' }}>{field}</span>
        {desc && (
          <span title={desc} className="cursor-help" style={{ color: 'var(--text-secondary)' }}>
            ?
          </span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <ValueCell field={field} value={value} />
        {desc && <div style={{ color: 'var(--text-secondary)' }} className="mt-0.5">{desc}</div>}
      </div>
    </div>
  )
}

// ── System.json 전용 뷰 ───────────────────────────────────────
function SystemView({ data, filename }) {
  const fieldDescs = FIELD_DESC[filename] ?? {}
  return (
    <div>
      {Object.entries(data).map(([field, value]) => (
        <FieldRow key={field} field={field} value={value} desc={fieldDescs[field]} />
      ))}
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
export default function GameDataViewer({ gameId, refreshKey }) {
  const [cache, setCache] = useState({})
  const [selectedFile, setSelectedFile] = useState('Enemies.json')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  // Clear cache when game data is updated by the AI
  useEffect(() => {
    setCache({})
  }, [refreshKey])

  useEffect(() => {
    if (cache[selectedFile]) return
    setIsLoading(true)
    setError(null)
    fetch(`/game/${gameId}/data/${selectedFile}`)
      .then((res) => {
        if (!res.ok) throw new Error('불러오기 실패')
        return res.json()
      })
      .then((data) => setCache((prev) => ({ ...prev, [selectedFile]: data })))
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
    // cache intentionally included — re-fetch after cache cleared by AI update
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, selectedFile, cache])

  const data = cache[selectedFile]
  const isArray = Array.isArray(data)
  const items = isArray ? data.filter(Boolean) : null // index 0 (null) 제거

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 파일 탭 */}
      <div
        className="flex gap-1 p-2 flex-shrink-0 flex-wrap"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        {DATA_FILES.map((f) => (
          <button
            key={f}
            onClick={() => setSelectedFile(f)}
            className="px-2 py-1 rounded text-xs transition-colors"
            style={{
              background: selectedFile === f ? 'var(--accent)' : 'var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            {f.replace('.json', '')}
          </button>
        ))}
      </div>

      {/* 콘텐츠 */}
      <div className="flex-1 overflow-y-auto p-3">
        {isLoading && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>로딩 중...</p>
        )}
        {error && (
          <p className="text-sm" style={{ color: '#e05555' }}>{error}</p>
        )}
        {!isLoading && !error && data && (
          <>
            <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
              {selectedFile}
              {isArray && ` — 총 ${items.length}개`}
            </p>
            {isArray
              ? items.map((item) => (
                  <ItemCard key={item.id} item={item} filename={selectedFile} />
                ))
              : <SystemView data={data} filename={selectedFile} />
            }
          </>
        )}
      </div>
    </div>
  )
}
