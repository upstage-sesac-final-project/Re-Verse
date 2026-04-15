import { useState, useEffect, useMemo } from 'react'

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

const DATA_FILES = ['Actors.json', 'Classes.json', 'Skills.json', 'Items.json', 'Weapons.json', 'Armors.json', 'Enemies.json', 'States.json', 'System.json']
const FILE_LABEL = { 'Actors.json': '액터', 'Classes.json': '직업', 'Skills.json': '스킬', 'Items.json': '아이템', 'Weapons.json': '무기', 'Armors.json': '방어구', 'Enemies.json': '적', 'States.json': '스테이트', 'System.json': '시스템' }
const REF_FILES = ['Weapons.json', 'Armors.json', 'Items.json', 'Skills.json', 'Classes.json', 'States.json']

// ── 유틸 ─────────────────────────────────────────────────────────
function ref(lookup, file, id) { return id && lookup?.[file]?.[id] || null }
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

function getActorParams(actor, classes) {
  const cls = classes?.find(c => c?.id === actor.classId)
  if (!cls?.params) return [0, 0, 0, 0, 0, 0, 0, 0]
  const level = actor.initialLevel ?? 1
  return cls.params.map(curve => Array.isArray(curve) ? (curve[level] ?? 0) : 0)
}

// ── 공용 UI 컴포넌트 (RPG Maker DB 스타일) ──────────────────────
function FieldGroup({ title, children, className = '' }) {
  return (
    <div className={`relative rounded border ${className}`} style={{ borderColor: 'var(--border)', padding: '14px 12px 10px' }}>
      {title && (
        <span className="absolute -top-2 left-2.5 px-1.5 text-[11px] font-medium" style={{ background: 'var(--bg-primary)', color: '#7aa2f7' }}>
          {title}
        </span>
      )}
      {children}
    </div>
  )
}

function Field({ label, value }) {
  return (
    <div className="flex items-baseline gap-2 py-0.5">
      <span className="text-[11px] flex-shrink-0 text-right" style={{ color: 'var(--text-secondary)', minWidth: 56 }}>{label}:</span>
      <span className="text-xs" style={{ color: 'var(--text-primary)' }}>{value ?? '—'}</span>
    </div>
  )
}

function SimpleTable({ columns, rows }) {
  if (!rows?.length) return <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>없음</p>
  return (
    <table className="w-full text-[11px]" style={{ borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          {columns.map((col, i) => (
            <th key={i} className="text-left py-1 px-2 font-medium" style={{ color: 'var(--text-secondary)' }}>{col}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
            {row.map((cell, ci) => (
              <td key={ci} className="py-1 px-2" style={{ color: 'var(--text-primary)' }}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function StatGrid({ params, showSign = false }) {
  return (
    <div className="grid grid-cols-4 gap-x-4 gap-y-1">
      {P.map((label, i) => {
        const v = params?.[i] ?? 0
        const display = showSign && v !== 0 ? `${v > 0 ? '+' : ''}${v}` : String(v)
        return (
          <div key={i} className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold tabular-nums" style={{ color: STAT_COLORS[i], width: 26, textAlign: 'right' }}>{label}</span>
            <span className="text-xs tabular-nums" style={{ color: v !== 0 ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{display}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── 상세 패널: 액터 ─────────────────────────────────────────────
function ActorDetail({ item, lookup, classes }) {
  const cls = ref(lookup, 'Classes.json', item.classId)
  const params = getActorParams(item, classes)
  const equips = item.equips || []
  const traits = (item.traits || []).filter(t => t?.code != null)

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '1fr minmax(160px, 0.5fr)' }}>
      <div className="space-y-3">
        <FieldGroup title="일반 설정">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="이름" value={item.name} />
            <Field label="닉네임" value={item.nickname} />
            <Field label="직업" value={cls || `#${item.classId}`} />
            <div />
            <Field label="초기 레벨" value={item.initialLevel ?? 1} />
            <Field label="최대 레벨" value={item.maxLevel ?? 99} />
          </div>
          {item.profile && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>프로필:</span>
              <p className="text-xs mt-0.5 whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.profile}</p>
            </div>
          )}
        </FieldGroup>
        <FieldGroup title={`초기 스탯 (Lv.${item.initialLevel ?? 1})`}>
          <StatGrid params={params} />
        </FieldGroup>
        <FieldGroup title="초기 장비">
          <SimpleTable columns={['유형', '장비 아이템']}
            rows={EQUIP_SLOTS.map((slot, i) => {
              const id = equips[i] || 0
              const f = i === 0 ? 'Weapons.json' : 'Armors.json'
              return [slot, id ? (ref(lookup, f, id) || `#${id}`) : '없음']
            })} />
        </FieldGroup>
      </div>
      <div className="space-y-3">
        <FieldGroup title="특성">
          <SimpleTable columns={['유형', '내용']}
            rows={traits.map(t => [TRAIT_CODES[t.code] || `코드${t.code}`, fmtTrait(t)])} />
        </FieldGroup>
        <FieldGroup title="메모">
          <p className="text-xs whitespace-pre-wrap min-h-[40px]" style={{ color: item.note ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
            {item.note || '(없음)'}
          </p>
        </FieldGroup>
      </div>
    </div>
  )
}

// ── 상세 패널: 직업 ─────────────────────────────────────────────
function ClassDetail({ item, lookup }) {
  const params = item.params || []
  const is2d = Array.isArray(params[0])
  const learnings = [...(item.learnings || [])].sort((a, b) => a.level - b.level)

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '1fr minmax(160px, 0.5fr)' }}>
      <div className="space-y-3">
        <FieldGroup title="일반 설정">
          <Field label="이름" value={item.name} />
        </FieldGroup>
        {is2d && (
          <FieldGroup title="성장 곡선 (Lv.1 → Lv.Max)">
            {params.slice(0, 8).map((curve, i) => {
              if (!Array.isArray(curve)) return null
              const lv1 = curve[1] ?? 0, lvMax = curve[curve.length - 1] ?? 0
              if (lv1 === 0 && lvMax === 0) return null
              return (
                <div key={i} className="flex items-center gap-2 py-0.5">
                  <span className="text-[11px] font-semibold tabular-nums" style={{ color: STAT_COLORS[i], width: 26, textAlign: 'right' }}>{P[i]}</span>
                  <span className="text-xs tabular-nums" style={{ color: 'var(--text-primary)', width: 36, textAlign: 'right' }}>{lv1}</span>
                  <div className="flex-1 h-1.5 rounded-full relative" style={{ background: 'var(--border)' }}>
                    <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: '100%', background: `linear-gradient(90deg, ${STAT_COLORS[i]}88, ${STAT_COLORS[i]}22)` }} />
                  </div>
                  <span className="text-xs tabular-nums font-medium" style={{ color: 'var(--text-primary)', width: 36 }}>{lvMax}</span>
                </div>
              )
            })}
          </FieldGroup>
        )}
      </div>
      <div className="space-y-3">
        <FieldGroup title="습득 스킬">
          <SimpleTable columns={['레벨', '스킬']}
            rows={learnings.map(l => [`Lv.${l.level}`, ref(lookup, 'Skills.json', l.skillId) || `#${l.skillId}`])} />
        </FieldGroup>
        {item.note && (
          <FieldGroup title="메모">
            <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.note}</p>
          </FieldGroup>
        )}
      </div>
    </div>
  )
}

// ── 상세 패널: 스킬 ─────────────────────────────────────────────
function SkillDetail({ item, lookup }) {
  const dmg = item.damage
  const effects = (item.effects || []).filter(e => e?.code)

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '1fr minmax(160px, 0.5fr)' }}>
      <div className="space-y-3">
        <FieldGroup title="일반 설정">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="이름" value={item.name} />
            <Field label="범위" value={SCOPE[item.scope] || '—'} />
            <Field label="MP 소비" value={item.mpCost ?? 0} />
            <Field label="TP 소비" value={item.tpCost ?? 0} />
            <Field label="성공률" value={`${item.successRate ?? 100}%`} />
            <Field label="연속 횟수" value={item.repeats ?? 1} />
          </div>
          {item.description && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>설명:</span>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-primary)' }}>{item.description}</p>
            </div>
          )}
        </FieldGroup>
        {dmg && dmg.type > 0 && (
          <FieldGroup title="데미지">
            <div className="grid grid-cols-2 gap-x-4">
              <Field label="타입" value={DMG_TYPE[dmg.type]} />
              <Field label="속성" value={dmg.elementId > 0 ? `#${dmg.elementId}` : '통상'} />
            </div>
            {dmg.formula && (
              <div className="mt-2 rounded px-3 py-1.5 font-mono text-xs" style={{ background: 'rgba(0,0,0,0.25)', color: 'var(--text-primary)' }}>
                {dmg.formula}
              </div>
            )}
          </FieldGroup>
        )}
      </div>
      <div className="space-y-3">
        <FieldGroup title="사용 효과">
          {effects.length > 0
            ? <SimpleTable columns={['효과']} rows={effects.map(e => [fmtEffect(e, lookup)])} />
            : <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>없음</p>
          }
        </FieldGroup>
        {item.note && (
          <FieldGroup title="메모">
            <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.note}</p>
          </FieldGroup>
        )}
      </div>
    </div>
  )
}

// ── 상세 패널: 아이템 ───────────────────────────────────────────
function ItemDetail({ item, lookup }) {
  const effects = (item.effects || []).filter(e => e?.code)

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '1fr minmax(160px, 0.5fr)' }}>
      <div className="space-y-3">
        <FieldGroup title="일반 설정">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="이름" value={item.name} />
            <Field label="가격" value={`${(item.price ?? 0).toLocaleString()} G`} />
            <Field label="범위" value={SCOPE[item.scope] || '—'} />
            <Field label="소비" value={item.consumable !== false ? '소비' : '비소비'} />
          </div>
          {item.description && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>설명:</span>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-primary)' }}>{item.description}</p>
            </div>
          )}
        </FieldGroup>
      </div>
      <div className="space-y-3">
        <FieldGroup title="사용 효과">
          {effects.length > 0
            ? <SimpleTable columns={['효과']} rows={effects.map(e => [fmtEffect(e, lookup)])} />
            : <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>없음</p>
          }
        </FieldGroup>
        {item.note && (
          <FieldGroup title="메모">
            <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.note}</p>
          </FieldGroup>
        )}
      </div>
    </div>
  )
}

// ── 상세 패널: 무기 / 방어구 ────────────────────────────────────
function EquipDetail({ item, lookup, isArmor }) {
  const traits = (item.traits || []).filter(t => t?.code != null)

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '1fr minmax(160px, 0.5fr)' }}>
      <div className="space-y-3">
        <FieldGroup title="일반 설정">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="이름" value={item.name} />
            <Field label="가격" value={`${(item.price ?? 0).toLocaleString()} G`} />
            {isArmor && <Field label="장비 유형" value={ETYPE[item.etypeId] || `유형${item.etypeId}`} />}
          </div>
          {item.description && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>설명:</span>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-primary)' }}>{item.description}</p>
            </div>
          )}
        </FieldGroup>
        <FieldGroup title="능력치 보정">
          <StatGrid params={item.params} showSign />
        </FieldGroup>
      </div>
      <div className="space-y-3">
        <FieldGroup title="특성">
          <SimpleTable columns={['유형', '내용']}
            rows={traits.map(t => [TRAIT_CODES[t.code] || `코드${t.code}`, fmtTrait(t)])} />
        </FieldGroup>
        {item.note && (
          <FieldGroup title="메모">
            <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.note}</p>
          </FieldGroup>
        )}
      </div>
    </div>
  )
}

// ── 상세 패널: 적 ───────────────────────────────────────────────
function EnemyDetail({ item, lookup }) {
  const params = item.params || []
  const drops = (item.dropItems || []).filter(d => d.kind > 0)
  const kindFile = { 1: 'Items.json', 2: 'Weapons.json', 3: 'Armors.json' }

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '1fr minmax(160px, 0.5fr)' }}>
      <div className="space-y-3">
        <FieldGroup title="일반 설정">
          <Field label="이름" value={item.name} />
        </FieldGroup>
        <FieldGroup title="능력치">
          <StatGrid params={params} />
        </FieldGroup>
        <FieldGroup title="보상">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="경험치" value={item.exp?.toLocaleString() ?? 0} />
            <Field label="골드" value={item.gold?.toLocaleString() ?? 0} />
          </div>
        </FieldGroup>
        {drops.length > 0 && (
          <FieldGroup title="드롭 아이템">
            <SimpleTable columns={['종류', '아이템', '확률']}
              rows={drops.map(d => [
                DROP_KIND[d.kind],
                ref(lookup, kindFile[d.kind], d.dataId) || `#${d.dataId}`,
                d.denominator > 0 ? `1/${d.denominator}` : '—',
              ])} />
          </FieldGroup>
        )}
      </div>
      <div className="space-y-3">
        <FieldGroup title="행동 패턴">
          {item.actions?.length > 0
            ? <SimpleTable columns={['스킬', '레이팅']}
                rows={item.actions.map(a => [
                  ref(lookup, 'Skills.json', a.skillId) || `스킬#${a.skillId}`,
                  String(a.rating),
                ])} />
            : <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>없음</p>
          }
        </FieldGroup>
        {item.traits?.length > 0 && (
          <FieldGroup title="특성">
            <SimpleTable columns={['유형', '내용']}
              rows={item.traits.filter(t => t?.code != null).map(t => [TRAIT_CODES[t.code] || `코드${t.code}`, fmtTrait(t)])} />
          </FieldGroup>
        )}
        {item.note && (
          <FieldGroup title="메모">
            <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.note}</p>
          </FieldGroup>
        )}
      </div>
    </div>
  )
}

// ── 상세 패널: 스테이트 ─────────────────────────────────────────
function StateDetail({ item }) {
  return (
    <div className="space-y-3">
      <FieldGroup title="일반 설정">
        <div className="grid grid-cols-2 gap-x-4">
          <Field label="이름" value={item.name} />
          <Field label="우선도" value={item.priority} />
          <Field label="제한" value={RESTRICTION[item.restriction] || '없음'} />
          {item.iconIndex > 0 && <Field label="아이콘" value={`#${item.iconIndex}`} />}
        </div>
      </FieldGroup>
      <FieldGroup title="자동 해제">
        <div className="grid grid-cols-2 gap-x-4">
          <Field label="지속 턴" value={(item.minTurns || item.maxTurns) ? `${item.minTurns ?? 0} ~ ${item.maxTurns ?? '∞'}` : '영구'} />
          <Field label="전투 종료" value={item.removeAtBattleEnd ? '해제' : '유지'} />
          <Field label="피격 해제" value={item.removeByDamage ? `${item.chanceByDamage ?? 100}%` : '안 함'} />
          <Field label="걸음 해제" value={item.removeByWalking ? `${item.stepsToRemove ?? 0}걸음` : '안 함'} />
        </div>
      </FieldGroup>
      {item.traits?.length > 0 && (
        <FieldGroup title="특성">
          <SimpleTable columns={['유형', '내용']}
            rows={item.traits.filter(t => t?.code != null).map(t => [TRAIT_CODES[t.code] || `코드${t.code}`, fmtTrait(t)])} />
        </FieldGroup>
      )}
      {item.note && (
        <FieldGroup title="메모">
          <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{item.note}</p>
        </FieldGroup>
      )}
    </div>
  )
}

// ── 상세 패널: 시스템 ───────────────────────────────────────────
function SystemDetail({ data, lookup }) {
  return (
    <div className="space-y-3">
      <FieldGroup title="기본 설정">
        <div className="grid grid-cols-2 gap-x-4">
          <Field label="게임 제목" value={data.gameTitle} />
          <Field label="화폐 단위" value={data.currencyUnit || 'G'} />
          <Field label="시작 맵" value={`맵 #${data.startMapId}`} />
          <Field label="시작 좌표" value={`(${data.startX}, ${data.startY})`} />
          <Field label="언어" value={data.locale || '—'} />
          <Field label="타일 크기" value={data.tileSize ? `${data.tileSize}px` : '48px'} />
        </div>
      </FieldGroup>
      <FieldGroup title="초기 파티">
        <div className="text-xs" style={{ color: 'var(--text-primary)' }}>
          {(data.partyMembers || []).map((id, i) => (
            <span key={id}>
              {i > 0 && ', '}
              {ref(lookup, 'Actors.json', id) || `#${id}`}
            </span>
          )) || '없음'}
        </div>
      </FieldGroup>
      <FieldGroup title="옵션">
        <div className="grid grid-cols-2 gap-x-4">
          <Field label="사이드뷰" value={data.optSideView ? '사용' : '미사용'} />
          <Field label="TP 표시" value={data.optDisplayTp ? '표시' : '숨김'} />
          <Field label="자동 전투" value={data.optAutoBattle ? '허용' : '불가'} />
          <Field label="대시" value={data.optExtraExp !== false ? '허용' : '불가'} />
        </div>
      </FieldGroup>
    </div>
  )
}

// ── 메인 컴포넌트 ────────────────────────────────────────────────
export default function GameDataViewer({ gameId, refreshKey }) {
  const [cache, setCache] = useState({})
  const [selectedFile, setSelectedFile] = useState('Actors.json')
  const [selectedItemId, setSelectedItemId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  // 카테고리 변경 시 초기화
  useEffect(() => { setSearch(''); setSelectedItemId(null) }, [selectedFile])
  useEffect(() => { setCache({}) }, [refreshKey])

  // 참조 데이터 프리로드
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

  // 선택된 파일 로드
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
  const isSystem = selectedFile === 'System.json'

  const items = useMemo(() => {
    if (!isArray) return null
    let list = data.filter(Boolean)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter((it) => (it.name && it.name.toLowerCase().includes(q)) || String(it.id) === q)
    }
    return list.sort((a, b) => a.id - b.id)
  }, [data, isArray, search])

  // 첫 아이템 자동 선택
  useEffect(() => {
    if (items?.length > 0 && (selectedItemId == null || !items.find(it => it.id === selectedItemId))) {
      setSelectedItemId(items[0].id)
    }
  }, [items, selectedItemId])

  const selectedItem = items?.find(it => it.id === selectedItemId)

  function renderDetail() {
    if (isSystem && data) return <SystemDetail data={data} lookup={lookup} />
    if (!selectedItem) return null
    const classes = Array.isArray(cache['Classes.json']) ? cache['Classes.json'] : []
    switch (selectedFile) {
      case 'Actors.json': return <ActorDetail item={selectedItem} lookup={lookup} classes={classes} />
      case 'Classes.json': return <ClassDetail item={selectedItem} lookup={lookup} />
      case 'Skills.json': return <SkillDetail item={selectedItem} lookup={lookup} />
      case 'Items.json': return <ItemDetail item={selectedItem} lookup={lookup} />
      case 'Weapons.json': return <EquipDetail item={selectedItem} lookup={lookup} />
      case 'Armors.json': return <EquipDetail item={selectedItem} lookup={lookup} isArmor />
      case 'Enemies.json': return <EnemyDetail item={selectedItem} lookup={lookup} />
      case 'States.json': return <StateDetail item={selectedItem} />
      default: return null
    }
  }

  return (
    <div className="flex-1 flex overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
      {/* ── 카테고리 사이드바 ── */}
      <div className="flex-shrink-0 flex flex-col overflow-y-auto" style={{ width: 88, background: '#1a1d28', borderRight: '1px solid var(--border)' }}>
        <div className="px-2 py-1.5 text-[10px] font-bold tracking-wider text-center" style={{ color: '#7aa2f7', borderBottom: '1px solid var(--border)', background: '#161926' }}>
          DATABASE
        </div>
        {DATA_FILES.map(f => (
          <button key={f} onClick={() => setSelectedFile(f)}
            className="text-left px-3 py-2 text-xs transition-colors"
            style={{
              background: selectedFile === f ? '#252d48' : 'transparent',
              color: selectedFile === f ? '#7aa2f7' : '#8892b0',
              borderLeft: selectedFile === f ? '2px solid #7aa2f7' : '2px solid transparent',
              fontWeight: selectedFile === f ? 600 : 400,
            }}>
            {FILE_LABEL[f]}
          </button>
        ))}
      </div>

      {/* ── 아이템 리스트 ── */}
      {!isSystem && (
        <div className="flex-shrink-0 flex flex-col overflow-hidden" style={{ width: 172, borderRight: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
          <div className="px-2.5 py-1.5 text-xs font-semibold flex-shrink-0 flex items-center justify-between" style={{ background: '#1e2130', color: '#7aa2f7', borderBottom: '1px solid var(--border)' }}>
            <span>{FILE_LABEL[selectedFile]}</span>
            {items && <span className="text-[10px] font-normal" style={{ color: '#8892b0' }}>{items.length}</span>}
          </div>
          <div className="px-1.5 py-1 flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="검색..."
              className="w-full px-1.5 py-0.5 text-[11px] rounded"
              style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', outline: 'none' }} />
          </div>
          <div className="flex-1 overflow-y-auto">
            {items?.map(item => (
              <div key={item.id} onClick={() => setSelectedItemId(item.id)}
                className="flex items-center px-2 py-[5px] cursor-pointer transition-colors"
                style={{
                  background: selectedItemId === item.id ? 'rgba(122, 162, 247, 0.12)' : 'transparent',
                  borderLeft: selectedItemId === item.id ? '2px solid #7aa2f7' : '2px solid transparent',
                }}>
                <span className="flex-shrink-0 tabular-nums text-[11px] mr-1.5" style={{ color: '#8892b0', width: 34 }}>
                  {String(item.id).padStart(4, '0')}
                </span>
                <span className="truncate text-[11px]" style={{ color: selectedItemId === item.id ? '#7aa2f7' : 'var(--text-primary)' }}>
                  {item.name || '(이름 없음)'}
                </span>
              </div>
            ))}
            {items?.length === 0 && (
              <div className="px-3 py-4 text-[11px] text-center" style={{ color: 'var(--text-secondary)' }}>
                {search ? '검색 결과 없음' : '데이터 없음'}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 상세 패널 ── */}
      <div className="flex-1 overflow-y-auto p-3 min-w-0">
        {isLoading && <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>로딩 중...</p>}
        {error && <p className="text-xs" style={{ color: '#e05555' }}>{error}</p>}
        {!isLoading && !error && data && renderDetail()}
        {!isLoading && !error && !data && (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>데이터를 선택하세요</p>
        )}
      </div>
    </div>
  )
}
