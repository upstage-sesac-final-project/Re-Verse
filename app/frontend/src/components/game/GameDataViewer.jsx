import { useState, useEffect, useMemo } from 'react'
import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, Radar } from 'recharts'

// ── RPG Maker MZ 코드 해석 ───────────────────────────────────────
const P = ['HP', 'MP', 'ATK', 'DEF', 'MAT', 'MDF', 'AGI', 'LUK']
const STAT_COLORS = ['#ef4444', '#3b82f6', '#f97316', '#22c55e', '#a855f7', '#06b6d4', '#eab308', '#ec4899']
const EQUIP_SLOTS = ['무기', '방패', '머리', '몸', '장신구']
const SCOPE = { 0: '없음', 1: '적 1체', 2: '적 전체', 3: '적 1체(랜덤)', 4: '적 2체(랜덤)', 5: '적 3체(랜덤)', 6: '적 4체(랜덤)', 7: '아군 1체', 8: '아군 전체', 9: '아군 1체(전투불능)', 10: '아군 전체(전투불능)', 11: '사용자' }
const DMG_TYPE = { 0: '없음', 1: 'HP 데미지', 2: 'MP 데미지', 3: 'HP 회복', 4: 'MP 회복', 5: 'HP 흡수', 6: 'MP 흡수' }
const DROP_KIND = { 1: '아이템', 2: '무기', 3: '방어구' }
const RESTRICTION = { 0: '없음', 1: '적 공격', 2: '아무나 공격', 3: '아군 공격', 4: '행동 불가' }
const ETYPE = { 1: '무기', 2: '방패', 3: '머리', 4: '몸', 5: '장신구' }

const TRAIT_CODES = { 11: '속성내성', 12: '디버프내성', 13: '상태내성', 14: '상태무효', 21: '능력치', 22: '추가능력', 23: '특수능력', 31: '공격속성', 32: '공격상태', 33: '공격속도', 34: '추가타', 41: '스킬타입+', 42: '스킬타입봉인', 43: '스킬+', 44: '스킬봉인', 51: '무기장착', 52: '방어구장착', 53: '장비고정', 54: '장비봉인', 55: '슬롯', 61: '행동추가', 62: '특수플래그', 63: '소멸', 64: '파티능력' }
const XPARAM = ['명중', '회피', '치명타', '치명타회피', 'MP회피', 'TP충전', '반격', 'HP재생', 'MP재생', 'TP재생']
const SPARAM = ['타겟율', '방어효과', '회복효과', '약학', 'MP소비', 'TP충전', '물리피해', '마법피해', '바닥피해', '경험치']
const EFFECT_CODES = { 11: 'HP회복', 12: 'MP회복', 13: 'TP획득', 21: '상태부여', 22: '상태해제', 31: '버프', 32: '디버프', 33: '버프해제', 34: '디버프해제', 41: '특수', 42: '성장', 43: '스킬습득', 44: '커먼이벤트' }

const DATA_FILES = ['Actors.json', 'Classes.json', 'Enemies.json', 'Skills.json', 'States.json', 'Items.json', 'Weapons.json', 'Armors.json', 'System.json']
const FILE_LABEL = { 'Actors.json': '캐릭터', 'Classes.json': '직업', 'Enemies.json': '적', 'Skills.json': '스킬', 'States.json': '상태', 'Items.json': '아이템', 'Weapons.json': '무기', 'Armors.json': '방어구', 'System.json': '시스템' }
const REF_FILES = ['Weapons.json', 'Armors.json', 'Items.json', 'Skills.json', 'Classes.json', 'States.json']

const SORT_OPTIONS = {
  'Actors.json': [['id', 'ID'], ['name', '이름']],
  'Enemies.json': [['id', 'ID'], ['name', '이름'], ['params.0', 'HP'], ['params.2', 'ATK'], ['exp', 'EXP']],
  'Skills.json': [['id', 'ID'], ['name', '이름'], ['mpCost', 'MP']],
  'Items.json': [['id', 'ID'], ['name', '이름'], ['price', '가격']],
  'Weapons.json': [['id', 'ID'], ['name', '이름'], ['params.2', 'ATK'], ['price', '가격']],
  'Armors.json': [['id', 'ID'], ['name', '이름'], ['params.3', 'DEF'], ['price', '가격']],
  'Classes.json': [['id', 'ID'], ['name', '이름']],
  'States.json': [['id', 'ID'], ['name', '이름'], ['priority', '우선도']],
}

// ── 유틸 ─────────────────────────────────────────────────────────
function ref(lookup, file, id) { return id && lookup?.[file]?.[id] || null }
function getVal(obj, path) { return path.split('.').reduce((o, k) => o?.[k], obj) ?? 0 }
function buildLookup(cache) {
  const lk = {}
  for (const f of REF_FILES) {
    const d = cache[f]; if (!Array.isArray(d)) continue
    const m = {}; d.forEach((it) => { if (it) m[it.id] = it.name }); lk[f] = m
  }
  return lk
}

function fmtTrait(t) {
  if (!t || t.code == null) return null
  const c = t.code, label = TRAIT_CODES[c] || `코드${c}`
  if (c === 21) return `${P[t.dataId] || '?'} ${Math.round(t.value * 100)}%`
  if (c === 22) { const v = Math.round(t.value * 100); return `${XPARAM[t.dataId] || '?'} ${v >= 0 ? '+' : ''}${v}%` }
  if (c === 23) return `${SPARAM[t.dataId] || '?'} ${Math.round(t.value * 100)}%`
  if (c === 33 || c === 34) return `${label} ${t.value >= 0 ? '+' : ''}${t.value}`
  if (c === 51 || c === 52 || c === 43 || c === 44) return `${label} #${t.dataId}`
  if (c === 61) return `${label} +${Math.round(t.value * 100)}%`
  if (t.dataId) return `${label} #${t.dataId}`
  return label
}

function fmtEffect(e, lookup) {
  const label = EFFECT_CODES[e.code] || `효과${e.code}`
  if (e.code === 11 || e.code === 12) {
    const p = []; if (e.value1) p.push(`${Math.round(e.value1 * 100)}%`); if (e.value2) p.push(`${e.value2 > 0 ? '+' : ''}${e.value2}`)
    return `${label} ${p.join(' ')}`
  }
  if (e.code === 13) return `${label} +${e.value1}`
  if (e.code === 21 || e.code === 22) {
    const name = lookup?.['States.json']?.[e.dataId] || `#${e.dataId}`
    return `${label} ${name} ${Math.round(e.value1 * 100)}%`
  }
  if (e.code === 31 || e.code === 32) return `${label} ${P[e.dataId] || '?'} ${e.value1}턴`
  if (e.code === 42) return `${label} ${P[e.dataId] || '?'} +${e.value1}`
  if (e.code === 43) {
    const name = lookup?.['Skills.json']?.[e.dataId] || `#${e.dataId}`
    return `${label} ${name}`
  }
  return label
}

function getThreatLevel(params) {
  const hp = params?.[0] || 0
  if (hp >= 5000) return 5
  if (hp >= 2000) return 4
  if (hp >= 500) return 3
  if (hp >= 100) return 2
  return 1
}

// ── 공용 컴포넌트 ────────────────────────────────────────────────
function StatBar({ label, value, max, color = 'var(--accent)' }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0
  return (
    <div className="flex items-center gap-1.5 text-xs py-0.5">
      <span className="w-8 text-right flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--border)' }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color, minWidth: pct > 0 ? '2px' : 0 }} />
      </div>
      <span className="w-12 text-right flex-shrink-0 tabular-nums" style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  )
}

function Badge({ children, color }) {
  return (
    <span className="inline-flex px-1.5 py-0.5 rounded text-xs whitespace-nowrap" style={{ background: color || 'var(--border)', color: 'var(--text-primary)' }}>
      {children}
    </span>
  )
}

function Tag({ children }) {
  return <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}>{children}</span>
}

function Section({ label, children }) {
  if (!children) return null
  return (
    <div className="mt-2">
      <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      {children}
    </div>
  )
}

// ── 캐릭터 스탯을 직업(Class) 성장곡선에서 도출 ────────────────
function getActorParams(actor, classes) {
  const cls = classes?.find(c => c?.id === actor.classId)
  if (!cls?.params) return [0, 0, 0, 0, 0, 0, 0, 0]
  const level = actor.initialLevel ?? 1
  return cls.params.map(curve => Array.isArray(curve) ? (curve[level] ?? 0) : 0)
}

// ── 캐릭터 카드 (Actors) — Design A: Radar + Enhanced Stats ─────
function ActorCard({ item, lookup, maxParams, classes }) {
  const cls = ref(lookup, 'Classes.json', item.classId)
  const params = getActorParams(item, classes)
  // 스탯별 정규화 (HP 수백 vs ATK 수십 스케일 차이 보정)
  const radarData = P.map((label, i) => ({ stat: label, value: maxParams[i] > 0 ? Math.round(((params[i] || 0) / maxParams[i]) * 100) : 0, fullMark: 100 }))

  return (
    <div className="rounded-xl mb-3 overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)', transition: 'border-color 0.3s, box-shadow 0.3s' }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.boxShadow = '0 0 20px rgba(233,69,96,0.1)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none' }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex-shrink-0 flex items-center justify-center rounded-lg text-base font-bold" style={{ width: 40, height: 40, background: 'linear-gradient(135deg, var(--accent), #a855f7)' }}>
          {(item.name || '?')[0]}
        </div>
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{item.name}</span>
            {item.nickname && <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{item.nickname}</span>}
          </div>
          <div className="flex gap-1.5 mt-1">
            {cls && <Badge color="rgba(139, 92, 246, 0.15)">{cls}</Badge>}
            <Tag>Lv.{item.initialLevel ?? 1}~{item.maxLevel ?? 99}</Tag>
          </div>
        </div>
      </div>
      {/* Body: Radar + Stats */}
      <div className="flex gap-4 p-4">
        <div className="flex-shrink-0" style={{ width: 160, height: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData} outerRadius="60%">
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="stat" tick={{ fill: '#8892b0', fontSize: 9, fontWeight: 500 }} />
              <Radar dataKey="value" stroke="#ff3b5c" fill="#ff3b5c" fillOpacity={0.15} strokeWidth={2} dot={{ r: 2.5, fill: '#ff3b5c', stroke: '#fff', strokeWidth: 1 }} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 min-w-0">
          {P.map((label, i) => {
            if (params[i] == null) return null
            const pct = maxParams[i] > 0 ? Math.min((params[i] / maxParams[i]) * 100, 100) : 0
            return (
              <div key={i} className="flex items-center gap-1.5 mb-1">
                <span className="text-right flex-shrink-0" style={{ width: 28, fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)' }}>{label}</span>
                <div className="flex-1 rounded-full overflow-hidden" style={{ height: 5, background: 'rgba(255,255,255,0.05)' }}>
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${STAT_COLORS[i]}cc, ${STAT_COLORS[i]})`, transition: 'width 0.4s ease' }} />
                </div>
                <span className="text-right flex-shrink-0 tabular-nums" style={{ width: 36, fontSize: 11, fontWeight: 600, color: STAT_COLORS[i] }}>{params[i]}</span>
              </div>
            )
          })}
          {(item.equips || []).some(id => id > 0) && (
            <div className="mt-3 flex flex-wrap gap-1">
              {(item.equips || []).map((id, i) => {
                if (!id) return null
                const f = i === 0 ? 'Weapons.json' : 'Armors.json'
                const name = ref(lookup, f, id)
                const isW = i === 0
                return <span key={i} className="text-xs px-2 py-0.5 rounded-md" style={{ background: isW ? 'rgba(249,115,22,0.1)' : 'rgba(59,130,246,0.1)', border: `1px solid ${isW ? 'rgba(249,115,22,0.2)' : 'rgba(59,130,246,0.2)'}`, color: isW ? '#f97316' : '#3b82f6' }}>{EQUIP_SLOTS[i]}: {name || `#${id}`}</span>
              })}
            </div>
          )}
          {item.traits?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {item.traits.slice(0, 4).map((t, i) => <Tag key={i}>{fmtTrait(t)}</Tag>)}
              {item.traits.length > 4 && <Tag>+{item.traits.length - 4}</Tag>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 적 카드 (Enemies) — Design F: Bestiary ──────────────────────
function EnemyCard({ item, lookup, maxParams }) {
  const params = item.params || []
  const drops = (item.dropItems || []).filter((d) => d.kind > 0)
  const kindFile = { 1: 'Items.json', 2: 'Weapons.json', 3: 'Armors.json' }
  const threat = getThreatLevel(params)

  return (
    <div className="rounded-xl mb-3 overflow-hidden" style={{ border: `1px solid ${threat >= 4 ? 'rgba(233,69,96,0.3)' : 'var(--border)'}`, background: 'var(--bg-secondary)' }}>
      {/* Header */}
      <div className="flex items-start justify-between px-4 py-3" style={{
        borderBottom: '1px solid var(--border)',
        background: threat >= 4 ? 'linear-gradient(90deg, rgba(233,69,96,0.05), transparent)' : undefined,
      }}>
        <span className="text-sm font-semibold" style={{ color: threat >= 4 ? 'var(--accent)' : 'var(--text-primary)' }}>{item.name}</span>
        <div className="text-right flex-shrink-0 ml-2">
          <div className="flex gap-1 justify-end">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="rounded-full" style={{ width: 7, height: 7, background: i <= threat ? 'var(--accent)' : 'rgba(255,255,255,0.08)', boxShadow: i <= threat ? '0 0 6px rgba(233,69,96,0.3)' : 'none' }} />
            ))}
          </div>
          <span style={{ fontSize: 10, color: threat >= 4 ? 'var(--accent)' : 'var(--text-secondary)' }}>Threat Lv.{threat}</span>
        </div>
      </div>

      <div className="p-4">
        {/* Stats Grid */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          {[0, 2, 3, 6].map(i => params[i] != null && params[i] > 0 ? (
            <div key={i} className="text-center rounded-lg py-2" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <div className="font-bold" style={{ fontSize: 15, color: STAT_COLORS[i] }}>{params[i].toLocaleString()}</div>
              <div style={{ fontSize: 9, color: 'var(--text-secondary)' }}>{P[i]}</div>
            </div>
          ) : null)}
        </div>

        {/* EXP / Gold */}
        <div className="flex gap-3 mb-3">
          {item.exp > 0 && <span className="text-xs"><span style={{ color: 'var(--text-secondary)' }}>EXP</span> <b style={{ color: '#a855f7' }}>{item.exp.toLocaleString()}</b></span>}
          {item.gold > 0 && <span className="text-xs"><span style={{ color: 'var(--text-secondary)' }}>Gold</span> <b style={{ color: '#eab308' }}>{item.gold.toLocaleString()}</b></span>}
        </div>

        {/* Actions */}
        {item.actions?.length > 0 && (
          <div className="mb-3">
            <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>Actions</div>
            <div className="flex flex-wrap gap-1.5">
              {item.actions.map((a, i) => {
                const name = ref(lookup, 'Skills.json', a.skillId)
                return <span key={i} className="text-xs px-2.5 py-1 rounded-md" style={{ background: 'rgba(249,115,22,0.1)', border: '1px solid rgba(249,115,22,0.15)' }}>{name || `스킬#${a.skillId}`} <span style={{ color: 'var(--text-secondary)' }}>R:{a.rating}</span></span>
              })}
            </div>
          </div>
        )}

        {/* Drops */}
        {drops.length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>Drops</div>
            <div className="flex flex-col gap-1.5">
              {drops.map((d, i) => {
                const name = ref(lookup, kindFile[d.kind], d.dataId)
                const pct = d.denominator > 0 ? Math.min((1 / d.denominator) * 100, 100) : 0
                return (
                  <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg" style={{ background: 'rgba(0,0,0,0.2)' }}>
                    <span className="text-xs flex-1" style={{ color: 'var(--text-primary)' }}>{name || `${DROP_KIND[d.kind]}#${d.dataId}`}</span>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <div style={{ width: 32, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 2, background: pct > 30 ? '#22c55e' : pct > 10 ? '#eab308' : '#ef4444', minWidth: 1 }} />
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>1/{d.denominator}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── 장비 카드 (Weapons / Armors) — 모든 비제로 스탯 표시 ────────
function EquipGridCard({ item, lookup, maxParams, filename }) {
  const params = item.params || []
  const nonzero = params.map((v, i) => ({ label: P[i], value: v, idx: i })).filter(s => s.value !== 0)

  return (
    <div className="rounded-xl overflow-hidden flex flex-col" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)', transition: 'border-color 0.3s' }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}>
      <div className="p-3 flex flex-col flex-1">
        <div className="flex items-baseline justify-between mb-1">
          <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{item.name}</span>
          {item.price > 0 && <span className="text-xs flex-shrink-0 ml-1 font-semibold" style={{ color: '#eab308' }}>{item.price.toLocaleString()}G</span>}
        </div>
        {filename === 'Armors.json' && item.etypeId && (
          <span className="text-xs mb-1.5" style={{ color: 'var(--text-secondary)' }}>{ETYPE[item.etypeId] || `유형${item.etypeId}`}</span>
        )}
        {/* 모든 비제로 스탯 바 */}
        {nonzero.map(({ label, value, idx }) => {
          const pct = maxParams[idx] > 0 ? Math.min((value / maxParams[idx]) * 100, 100) : 0
          return (
            <div key={idx} className="flex items-center gap-1.5 mb-1">
              <span style={{ width: 28, fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'right' }}>{label}</span>
              <div className="flex-1 rounded-full overflow-hidden" style={{ height: 5, background: 'rgba(255,255,255,0.05)' }}>
                <div className="h-full rounded-full" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${STAT_COLORS[idx]}cc, ${STAT_COLORS[idx]})`, transition: 'width 0.4s ease' }} />
              </div>
              <span style={{ width: 28, fontSize: 11, fontWeight: 600, color: STAT_COLORS[idx], textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
            </div>
          )
        })}
        {item.traits?.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {item.traits.slice(0, 3).map((t, i) => <Tag key={i}>{fmtTrait(t)}</Tag>)}
            {item.traits.length > 3 && <Tag>+{item.traits.length - 3}</Tag>}
          </div>
        )}
      </div>
    </div>
  )
}

// ── 스킬 카드 (Skills) ───────────────────────────────────────────
function SkillRow({ item, lookup }) {
  const dmg = item.damage
  const hasCost = item.mpCost > 0 || item.tpCost > 0
  const dmgColor = dmg?.type >= 1 && dmg?.type <= 2 ? '#ef4444' : dmg?.type >= 3 && dmg?.type <= 4 ? '#22c55e' : dmg?.type >= 5 ? '#eab308' : null

  return (
    <div className="rounded-xl mb-2 overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)', transition: 'border-color 0.3s' }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
        <span className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{item.name}</span>
        {hasCost && (
          <div className="flex gap-1.5 flex-shrink-0">
            {item.mpCost > 0 && <span className="text-xs px-2 py-0.5 rounded-md font-semibold" style={{ background: 'rgba(59,130,246,0.1)', color: '#3b82f6' }}>MP {item.mpCost}</span>}
            {item.tpCost > 0 && <span className="text-xs px-2 py-0.5 rounded-md font-semibold" style={{ background: 'rgba(34,197,94,0.1)', color: '#22c55e' }}>TP {item.tpCost}</span>}
          </div>
        )}
      </div>
      {/* Body */}
      <div className="px-4 py-2.5">
        <div className="flex flex-wrap gap-1.5 mb-2">
          {dmg && dmg.type > 0 && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: `${dmgColor}15`, color: dmgColor }}>{DMG_TYPE[dmg.type]}</span>}
          {item.scope > 0 && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)' }}>{SCOPE[item.scope]}</span>}
          {item.successRate < 100 && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(234,179,8,0.1)', color: '#eab308' }}>명중 {item.successRate}%</span>}
          {item.repeats > 1 && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(236,72,153,0.1)', color: '#ec4899' }}>{item.repeats}연속</span>}
        </div>
        {dmg?.formula && (
          <div className="rounded-lg px-3 py-1.5 mb-2 font-mono text-xs" style={{ background: 'rgba(0,0,0,0.25)', color: 'var(--text-secondary)' }}>
            {dmg.formula}
          </div>
        )}
        {item.effects?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {item.effects.map((e, i) => <span key={i} className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(168,85,247,0.1)', color: '#a855f7' }}>{fmtEffect(e, lookup)}</span>)}
          </div>
        )}
      </div>
    </div>
  )
}

// ── 아이템 그리드 (Items) ────────────────────────────────────────
function ItemGridCard({ item }) {
  const hpEff = item.effects?.find((e) => e.code === 11)
  const mpEff = item.effects?.find((e) => e.code === 12)

  return (
    <div className="rounded-xl overflow-hidden flex flex-col" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)', transition: 'border-color 0.3s' }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}>
      <div className="p-3 flex flex-col flex-1">
        <div className="flex items-baseline justify-between mb-1">
          <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{item.name}</span>
          {item.price > 0 && <span className="text-xs flex-shrink-0 ml-1 font-semibold" style={{ color: '#eab308' }}>{item.price.toLocaleString()}G</span>}
        </div>
        {item.description && <span className="text-xs mb-2 line-clamp-1" style={{ color: 'var(--text-secondary)' }}>{item.description}</span>}
        <div className="flex flex-wrap gap-1 mt-auto">
          {item.scope > 0 && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)' }}>{SCOPE[item.scope]}</span>}
          {hpEff && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}>HP {hpEff.value1 ? `${Math.round(hpEff.value1 * 100)}%` : ''}{hpEff.value2 ? `+${hpEff.value2}` : ''}</span>}
          {mpEff && <span className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(59,130,246,0.1)', color: '#3b82f6' }}>MP {mpEff.value1 ? `${Math.round(mpEff.value1 * 100)}%` : ''}{mpEff.value2 ? `+${mpEff.value2}` : ''}</span>}
          {item.effects?.filter((e) => e.code !== 11 && e.code !== 12).slice(0, 2).map((e, i) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-md" style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)' }}>{fmtEffect(e)}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── 직업 카드 (Classes) ──────────────────────────────────────────
function ClassCard({ item, lookup }) {
  const params = item.params || []
  const is2d = Array.isArray(params[0])
  const learnings = [...(item.learnings || [])].sort((a, b) => a.level - b.level)
  return (
    <div className="rounded-lg p-3 mb-2" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{item.name}</span>
        {learnings.length > 0 && <Tag>스킬 {learnings.length}개</Tag>}
      </div>
      {/* 성장 곡선 */}
      {is2d && (
        <div className="mb-2">
          {params.slice(0, 8).map((curve, i) => {
            if (!Array.isArray(curve)) return null
            const lv1 = curve[1] ?? 0, lvMax = curve[curve.length - 1] ?? 0
            if (lv1 === 0 && lvMax === 0) return null
            return (
              <div key={i} className="flex items-center gap-2 text-xs py-0.5">
                <span className="w-8 text-right flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{P[i]}</span>
                <span className="w-10 text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{lv1}</span>
                <div className="flex-1 h-1.5 rounded-full relative" style={{ background: 'var(--border)' }}>
                  <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: '100%', background: `linear-gradient(90deg, ${i === 0 ? '#ef4444' : i === 1 ? '#3b82f6' : 'var(--accent)'} 0%, transparent 100%)`, opacity: 0.4 }} />
                </div>
                <span className="w-10 text-left tabular-nums font-medium" style={{ color: 'var(--text-primary)' }}>{lvMax}</span>
              </div>
            )
          })}
        </div>
      )}
      {/* 습득 스킬 타임라인 */}
      {learnings.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {learnings.map((l, i) => {
            const name = ref(lookup, 'Skills.json', l.skillId)
            return <Badge key={i} color="rgba(139, 92, 246, 0.1)">Lv.{l.level} {name || `#${l.skillId}`}</Badge>
          })}
        </div>
      )}
    </div>
  )
}

// ── 상태 행 (States) ─────────────────────────────────────────────
function StateRow({ item }) {
  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-lg mb-1" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
      <span className="text-sm font-medium w-24 truncate flex-shrink-0" style={{ color: 'var(--text-primary)' }}>{item.name}</span>
      <div className="flex gap-1.5 flex-wrap flex-1">
        {item.restriction > 0 && <Badge color="rgba(239, 68, 68, 0.15)">{RESTRICTION[item.restriction]}</Badge>}
        <Tag>우선도 {item.priority}</Tag>
        {(item.minTurns > 0 || item.maxTurns > 0) && <Tag>{item.minTurns ?? 0}~{item.maxTurns ?? '∞'}턴</Tag>}
        {item.removeAtBattleEnd && <Tag>전투 종료 시 해제</Tag>}
        {item.removeByDamage && <Tag>피격 해제 {item.chanceByDamage}%</Tag>}
        {item.removeByWalking && <Tag>{item.stepsToRemove}걸음 해제</Tag>}
      </div>
    </div>
  )
}

// ── 시스템 대시보드 (System) ──────────────────────────────────────
function SystemDashboard({ data, lookup }) {
  const cards = [
    { label: '게임 제목', value: data.gameTitle },
    { label: '시작 위치', value: `맵 #${data.startMapId} (${data.startX}, ${data.startY})` },
    { label: '파티 멤버', value: (data.partyMembers || []).map((id) => ref(lookup, 'Actors.json', id) || `#${id}`).join(', ') || '없음' },
    { label: '화폐', value: data.currency || 'G' },
    { label: '사이드뷰', value: data.optSideView ? '사용' : '미사용' },
    { label: 'TP 표시', value: data.optDisplayTp ? '표시' : '숨김' },
    { label: '언어', value: data.locale },
    { label: '타일 크기', value: data.tileSize ? `${data.tileSize}px` : '48px' },
  ]
  // Actors lookup for partyMembers — pre-build
  const actorLookup = useMemo(() => {
    // build actor lookup from lookup itself won't work, we need a separate one
    // but we can reuse the existing mechanism
    return {}
  }, [])

  return (
    <div className="grid grid-cols-2 gap-2">
      {cards.map((c) => (
        <div key={c.label} className="rounded-lg p-3" style={{ border: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
          <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{c.label}</div>
          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{c.value || '—'}</div>
        </div>
      ))}
    </div>
  )
}

// ── 최대값 계산 (스탯 바 스케일링용) ──────────────────────────────
function calcMaxParams(items) {
  const max = [0, 0, 0, 0, 0, 0, 0, 0]
  for (const item of items) {
    const p = item.params; if (!Array.isArray(p)) continue
    for (let i = 0; i < 8; i++) max[i] = Math.max(max[i], typeof p[i] === 'number' ? p[i] : 0)
  }
  return max
}

function calcMaxStat(items, index) {
  let max = 0
  for (const item of items) {
    const p = item.params; if (!Array.isArray(p)) continue
    max = Math.max(max, p[index] || 0)
  }
  return max
}

// ── 메인 컴포넌트 ────────────────────────────────────────────────
export default function GameDataViewer({ gameId, refreshKey }) {
  const [cache, setCache] = useState({})
  const [selectedFile, setSelectedFile] = useState('Actors.json')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('id')
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => { setSearch(''); setSortKey('id'); setSortAsc(true) }, [selectedFile])
  useEffect(() => { setCache({}) }, [refreshKey])

  useEffect(() => {
    REF_FILES.forEach((f) => {
      if (cache[f]) return
      fetch(`/game/${gameId}/data/${f}?v=${refreshKey}`, { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : null)
        .then((d) => { if (d) setCache((prev) => ({ ...prev, [f]: d })) })
        .catch(() => {})
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, refreshKey])

  useEffect(() => {
    if (cache[selectedFile]) return
    setIsLoading(true); setError(null)
    fetch(`/game/${gameId}/data/${selectedFile}?v=${refreshKey}`, { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error('불러오기 실패'); return r.json() })
      .then((d) => setCache((prev) => ({ ...prev, [selectedFile]: d })))
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, selectedFile, cache, refreshKey])

  const lookup = buildLookup(cache)
  const data = cache[selectedFile]
  const isArray = Array.isArray(data)

  const items = useMemo(() => {
    if (!isArray) return null
    let list = data.filter(Boolean)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter((it) => (it.name && it.name.toLowerCase().includes(q)) || String(it.id) === q)
    }
    list = [...list].sort((a, b) => {
      const av = getVal(a, sortKey), bv = getVal(b, sortKey)
      if (typeof av === 'string' && typeof bv === 'string') return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av)
      return sortAsc ? (av > bv ? 1 : -1) : (bv > av ? 1 : -1)
    })
    return list
  }, [data, isArray, search, sortKey, sortAsc])

  const maxParams = useMemo(() => items ? calcMaxParams(items) : [], [items])
  const sortOptions = SORT_OPTIONS[selectedFile] || [['id', 'ID'], ['name', '이름']]
  const isGrid = ['Weapons.json', 'Armors.json', 'Items.json'].includes(selectedFile)

  // 타입별 렌더
  function renderItems() {
    if (!items) return null
    switch (selectedFile) {
      case 'Actors.json': {
        const classes = Array.isArray(cache['Classes.json']) ? cache['Classes.json'] : []
        const actorMaxP = [0,0,0,0,0,0,0,0]
        items.forEach(it => { const p = getActorParams(it, classes); p.forEach((v, i) => { actorMaxP[i] = Math.max(actorMaxP[i], v) }) })
        return items.map((it) => <ActorCard key={it.id} item={it} lookup={lookup} maxParams={actorMaxP} classes={classes} />)
      }
      case 'Enemies.json':
        return items.map((it) => <EnemyCard key={it.id} item={it} lookup={lookup} maxParams={maxParams} />)
      case 'Classes.json':
        return items.map((it) => <ClassCard key={it.id} item={it} lookup={lookup} />)
      case 'Skills.json':
        return items.map((it) => <SkillRow key={it.id} item={it} lookup={lookup} />)
      case 'States.json':
        return items.map((it) => <StateRow key={it.id} item={it} />)
      case 'Items.json':
        return <div className="grid grid-cols-2 gap-2">{items.map((it) => <ItemGridCard key={it.id} item={it} />)}</div>
      case 'Weapons.json':
      case 'Armors.json': {
        const mp = calcMaxParams(items)
        return <div className="grid grid-cols-2 gap-2">{items.map((it) => <EquipGridCard key={it.id} item={it} lookup={lookup} maxParams={mp} filename={selectedFile} />)}</div>
      }
      default:
        return null
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 탭 */}
      <div className="flex gap-1 p-2 flex-shrink-0 flex-wrap" style={{ borderBottom: '1px solid var(--border)' }}>
        {DATA_FILES.map((f) => (
          <button key={f} onClick={() => setSelectedFile(f)}
            className="px-2.5 py-1 rounded text-xs transition-colors"
            style={{ background: selectedFile === f ? 'var(--accent)' : 'var(--border)', color: 'var(--text-primary)' }}
          >{FILE_LABEL[f]}</button>
        ))}
      </div>

      {/* 툴바 */}
      {isArray && items && (
        <div className="flex items-center gap-2 px-3 py-1.5 flex-shrink-0 flex-wrap" style={{ borderBottom: '1px solid var(--border)' }}>
          <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="이름 검색..." className="px-2 py-1 rounded text-xs flex-1 min-w-[100px]"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', color: 'var(--text-primary)', outline: 'none' }}
          />
          <div className="flex items-center gap-1">
            {sortOptions.map(([key, label]) => (
              <button key={key}
                onClick={() => { if (sortKey === key) setSortAsc((p) => !p); else { setSortKey(key); setSortAsc(true) } }}
                className="px-1.5 py-0.5 rounded text-xs"
                style={{ background: sortKey === key ? 'var(--accent)' : 'var(--border)', color: 'var(--text-primary)' }}
              >{label}{sortKey === key ? (sortAsc ? ' ↑' : ' ↓') : ''}</button>
            ))}
          </div>
        </div>
      )}

      {/* 콘텐츠 */}
      <div className="flex-1 overflow-y-auto p-3">
        {isLoading && <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>로딩 중...</p>}
        {error && <p className="text-sm" style={{ color: '#e05555' }}>{error}</p>}
        {!isLoading && !error && data && (
          <>
            <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
              {FILE_LABEL[selectedFile]} {isArray && `— ${search ? `${items.length}개 검색됨` : `총 ${items.length}개`}`}
            </p>
            {isArray
              ? renderItems()
              : <SystemDashboard data={data} lookup={lookup} />
            }
          </>
        )}
      </div>
    </div>
  )
}
