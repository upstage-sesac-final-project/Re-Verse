import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/layout/Header'
import {
  BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import * as adminApi from '../services/adminApi'
import { authFetch } from '../services/api'

const TABS = ['개요', '유저 트렌드', '사용량', '헬스', '공지 관리']

function StatCard({ label, value, sub }) {
  return (
    <div
      className="rounded-xl p-5 flex-1 min-w-[140px]"
      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
    >
      <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{value}</p>
      {sub && <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{sub}</p>}
    </div>
  )
}

function PeriodToggle({ period, onChange }) {
  return (
    <div className="flex gap-1 mb-4">
      {['daily', 'monthly'].map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className="px-3 py-1 text-xs rounded-lg"
          style={{
            background: period === p ? 'var(--accent)' : 'var(--border)',
            color: period === p ? '#fff' : 'var(--text-secondary)',
          }}
        >
          {p === 'daily' ? '일별' : '월별'}
        </button>
      ))}
    </div>
  )
}

function HealthBadge({ label, ok, detail }) {
  return (
    <div
      className="rounded-xl p-5"
      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-3 h-3 rounded-full"
          style={{ background: ok ? '#22c55e' : '#ef4444' }}
        />
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</span>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{detail}</p>
    </div>
  )
}

const chartStyle = { fontSize: 11, fill: '#999' }

export default function Admin() {
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)

  const [overview, setOverview] = useState(null)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [overviewError, setOverviewError] = useState(false)
  const [signups, setSignups] = useState([])
  const [logins, setLogins] = useState([])
  const [usage, setUsage] = useState([])
  const [intents, setIntents] = useState([])
  const [health, setHealth] = useState(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [healthError, setHealthError] = useState(false)

  const [signupPeriod, setSignupPeriod] = useState('daily')
  const [usagePeriod, setUsagePeriod] = useState('daily')

  function loadOverview() {
    setOverviewLoading(true)
    setOverviewError(false)
    adminApi.fetchOverview()
      .then(setOverview)
      .catch(() => setOverviewError(true))
      .finally(() => setOverviewLoading(false))
  }

  useEffect(() => {
    loadOverview()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const days = signupPeriod === 'monthly' ? 365 : 30
    adminApi.fetchSignups(signupPeriod, days).then(setSignups).catch((e) => console.error('[Admin]', e))
    adminApi.fetchLogins(signupPeriod, days).then(setLogins).catch((e) => console.error('[Admin]', e))
  }, [signupPeriod])

  useEffect(() => {
    const days = usagePeriod === 'monthly' ? 365 : 30
    adminApi.fetchUsage(usagePeriod, days).then(setUsage).catch((e) => console.error('[Admin]', e))
  }, [usagePeriod])

  useEffect(() => {
    adminApi.fetchIntents().then(setIntents).catch((e) => console.error('[Admin]', e))
  }, [])

  function loadHealth() {
    setHealthLoading(true)
    setHealthError(false)
    adminApi.fetchHealth()
      .then(setHealth)
      .catch(() => setHealthError(true))
      .finally(() => setHealthLoading(false))
  }

  useEffect(() => {
    if (tab !== 3) return
    loadHealth()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header />

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex gap-0 mb-8" style={{ borderBottom: '1px solid var(--border)' }}>
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              className="px-4 py-2.5 text-xs font-medium relative"
              style={{ color: tab === i ? 'var(--text-primary)' : 'var(--text-secondary)' }}
            >
              {t}
              {tab === i && <span className="absolute bottom-0 left-0 right-0 h-0.5" style={{ background: 'var(--accent)' }} />}
            </button>
          ))}
        </div>

        {/* 개요 탭 */}
        {tab === 0 && (
          overviewLoading ? (
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>불러오는 중...</p>
          ) : overview ? (
            <div className="flex flex-wrap gap-4">
              <StatCard label="총 유저" value={overview.total_users} />
              <StatCard label="총 프로젝트" value={overview.total_projects} />
              <StatCard label="총 대화" value={overview.total_conversations} />
              <StatCard label="성공률" value={`${(overview.success_rate * 100).toFixed(1)}%`} />
              <StatCard label="평균 응답시간" value={`${overview.avg_processing_time}s`} />
            </div>
          ) : overviewError ? (
            <div className="flex items-center gap-3">
              <p className="text-sm" style={{ color: '#f87171' }}>통계를 불러올 수 없습니다.</p>
              <button
                onClick={loadOverview}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                재시도
              </button>
            </div>
          ) : null
        )}

        {/* 유저 트렌드 탭 */}
        {tab === 1 && (
          <>
            <PeriodToggle period={signupPeriod} onChange={setSignupPeriod} />
            <div className="mb-8">
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                신규 가입
              </h3>
              <div style={{ width: '100%', height: 280 }}>
                <ResponsiveContainer>
                  <BarChart data={signups}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis dataKey="date" tick={chartStyle} />
                    <YAxis tick={chartStyle} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#ff3b5c" name="가입" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                로그인 수
              </h3>
              <div style={{ width: '100%', height: 280 }}>
                <ResponsiveContainer>
                  <BarChart data={logins}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis dataKey="date" tick={chartStyle} />
                    <YAxis tick={chartStyle} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#3b82f6" name="로그인" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}

        {/* 사용량 탭 */}
        {tab === 2 && (
          <>
            <PeriodToggle period={usagePeriod} onChange={setUsagePeriod} />
            <div className="mb-8">
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                API 사용량
              </h3>
              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                  <AreaChart data={usage}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis dataKey="date" tick={chartStyle} />
                    <YAxis tick={chartStyle} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="total" stroke="#999" fill="#3d3d3d" name="전체" />
                    <Area type="monotone" dataKey="success" stroke="#22c55e" fill="#22c55e33" name="성공" />
                    <Area type="monotone" dataKey="failed" stroke="#ef4444" fill="#ef444433" name="실패" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                Intent 분포
              </h3>
              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                  <BarChart data={intents} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis type="number" tick={chartStyle} allowDecimals={false} />
                    <YAxis type="category" dataKey="intent" tick={chartStyle} width={120} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#ff3b5c" name="횟수" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}

        {/* 공지 관리 탭 */}
        {tab === 4 && <NoticeManager />}

        {/* 헬스 탭 */}
        {tab === 3 && (
          healthLoading ? (
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>헬스 체크 중...</p>
          ) : healthError ? (
            <div className="flex items-center gap-3">
              <p className="text-sm" style={{ color: '#f87171' }}>헬스 체크에 실패했습니다.</p>
              <button
                onClick={loadHealth}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                재시도
              </button>
            </div>
          ) : health ? (
            <div className="flex flex-col gap-4">
              <HealthBadge label="Database" ok={health.db.ok} detail={health.db.detail} />
              <HealthBadge label="S3 Storage" ok={health.s3.ok} detail={health.s3.detail} />
              {overview && (
                <div
                  className="rounded-xl p-5"
                  style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
                >
                  <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
                    성능 지표
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    평균 응답시간: {overview.avg_processing_time}s / 성공률: {(overview.success_rate * 100).toFixed(1)}%
                  </p>
                </div>
              )}
            </div>
          ) : null
        )}
      </main>
    </div>
  )
}

// ── 공지 관리 컴포넌트 ──────────────────────────────────────────

const CHANGE_TYPES = ['new', 'fix', 'improve', 'remove']
const CHANGE_LABEL = { new: 'NEW', fix: 'FIX', improve: '개선', remove: '제거' }

const emptyAnnouncement = { title: '', content: '', date: new Date().toISOString().slice(0, 10), pinned: false }
const emptyPatchNote = { version: '', title: '', date: new Date().toISOString().slice(0, 10), changes: [{ type: 'new', text: '' }] }

function NoticeManager() {
  const [subTab, setSubTab] = useState('patch')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null) // null | 'new' | item object
  const [form, setForm] = useState({})

  function load() {
    setLoading(true)
    const endpoint = subTab === 'patch' ? '/v1/notices/admin/patch-notes' : '/v1/notices/admin/announcements'
    authFetch(endpoint)
      .then(data => { setItems(data); setEditing(null) })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [subTab])

  function startCreate() {
    setForm(subTab === 'patch' ? { ...emptyPatchNote, changes: [{ type: 'new', text: '' }] } : { ...emptyAnnouncement })
    setEditing('new')
  }

  function startEdit(item) {
    setForm({ ...item })
    setEditing(item)
  }

  async function handleSave() {
    const isPatch = subTab === 'patch'
    const isNew = editing === 'new'
    const endpoint = isPatch
      ? isNew ? '/v1/notices/patch-notes' : `/v1/notices/patch-notes/${form.id}`
      : isNew ? '/v1/notices/announcements' : `/v1/notices/announcements/${form.id}`
    await authFetch(endpoint, { method: isNew ? 'POST' : 'PUT', body: JSON.stringify(form) })
    load()
  }

  async function handleDelete(id) {
    if (!confirm('삭제하시겠습니까?')) return
    const endpoint = subTab === 'patch' ? `/v1/notices/patch-notes/${id}` : `/v1/notices/announcements/${id}`
    await authFetch(endpoint, { method: 'DELETE' })
    load()
  }

  async function handleTogglePublish(item) {
    const endpoint = subTab === 'patch' ? `/v1/notices/patch-notes/${item.id}` : `/v1/notices/announcements/${item.id}`
    await authFetch(endpoint, { method: 'PUT', body: JSON.stringify({ is_published: !item.is_published }) })
    load()
  }

  return (
    <div>
      {/* 서브탭 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-1">
          {[['patch', '패치노트'], ['announce', '공지사항']].map(([key, label]) => (
            <button key={key} onClick={() => { setSubTab(key); setEditing(null) }}
              className="px-3 py-1 text-xs rounded-lg"
              style={{ background: subTab === key ? 'var(--accent)' : 'var(--border)', color: subTab === key ? '#fff' : 'var(--text-secondary)' }}>
              {label}
            </button>
          ))}
        </div>
        <button onClick={startCreate} className="px-3 py-1.5 text-xs rounded-lg font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>
          + 새로 작성
        </button>
      </div>

      {/* 편집 폼 */}
      {editing && (
        <div className="rounded-xl p-4 mb-4" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
          <h4 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            {editing === 'new' ? '새로 작성' : '수정'}
          </h4>
          {subTab === 'patch' ? (
            <PatchNoteForm form={form} onChange={setForm} />
          ) : (
            <AnnouncementForm form={form} onChange={setForm} />
          )}
          <div className="flex gap-2 mt-3 justify-end">
            <button onClick={() => setEditing(null)} className="px-3 py-1.5 text-xs rounded-lg" style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}>취소</button>
            <button onClick={handleSave} className="px-3 py-1.5 text-xs rounded-lg font-medium" style={{ background: 'var(--accent)', color: '#fff' }}>저장</button>
          </div>
        </div>
      )}

      {/* 목록 */}
      {loading ? (
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>불러오는 중...</p>
      ) : items.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>항목이 없습니다.</p>
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id} className="rounded-xl px-4 py-3 flex items-center justify-between"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', opacity: item.is_published ? 1 : 0.5 }}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {subTab === 'patch' && <span className="text-xs font-semibold" style={{ color: 'var(--accent)' }}>{item.version}</span>}
                  <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{item.title}</span>
                  <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{item.date}</span>
                  {!item.is_published && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }}>비공개</span>}
                  {item.pinned && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255,59,92,0.12)', color: 'var(--accent)' }}>고정</span>}
                </div>
                {subTab === 'patch' && item.changes && (
                  <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>변경 {item.changes.length}건</p>
                )}
              </div>
              <div className="flex gap-1 flex-shrink-0 ml-3">
                <button onClick={() => handleTogglePublish(item)} className="px-2 py-1 text-[11px] rounded"
                  style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}>
                  {item.is_published ? '숨기기' : '공개'}
                </button>
                <button onClick={() => startEdit(item)} className="px-2 py-1 text-[11px] rounded"
                  style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}>수정</button>
                <button onClick={() => handleDelete(item.id)} className="px-2 py-1 text-[11px] rounded"
                  style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>삭제</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function inputStyle() {
  return { background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', outline: 'none' }
}

function AnnouncementForm({ form, onChange }) {
  const set = (k, v) => onChange({ ...form, [k]: v })
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_120px] gap-2">
        <input value={form.title || ''} onChange={e => set('title', e.target.value)} placeholder="제목"
          className="px-3 py-1.5 text-xs rounded-lg" style={inputStyle()} />
        <input type="date" value={form.date || ''} onChange={e => set('date', e.target.value)}
          className="px-3 py-1.5 text-xs rounded-lg" style={inputStyle()} />
      </div>
      <textarea value={form.content || ''} onChange={e => set('content', e.target.value)} placeholder="내용"
        rows={4} className="w-full px-3 py-2 text-xs rounded-lg resize-none" style={inputStyle()} />
      <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={form.pinned || false} onChange={e => set('pinned', e.target.checked)} />
        상단 고정
      </label>
    </div>
  )
}

function PatchNoteForm({ form, onChange }) {
  const set = (k, v) => onChange({ ...form, [k]: v })
  const changes = form.changes || []

  function setChange(idx, key, val) {
    const next = changes.map((c, i) => i === idx ? { ...c, [key]: val } : c)
    set('changes', next)
  }
  function addChange() { set('changes', [...changes, { type: 'new', text: '' }]) }
  function removeChange(idx) { set('changes', changes.filter((_, i) => i !== idx)) }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[80px_1fr_120px] gap-2">
        <input value={form.version || ''} onChange={e => set('version', e.target.value)} placeholder="v0.0.0"
          className="px-3 py-1.5 text-xs rounded-lg" style={inputStyle()} />
        <input value={form.title || ''} onChange={e => set('title', e.target.value)} placeholder="제목"
          className="px-3 py-1.5 text-xs rounded-lg" style={inputStyle()} />
        <input type="date" value={form.date || ''} onChange={e => set('date', e.target.value)}
          className="px-3 py-1.5 text-xs rounded-lg" style={inputStyle()} />
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>변경 사항</span>
          <button onClick={addChange} className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}>+ 추가</button>
        </div>
        {changes.map((c, i) => (
          <div key={i} className="flex gap-1.5 items-center">
            <select value={c.type} onChange={e => setChange(i, 'type', e.target.value)}
              className="px-2 py-1.5 text-[11px] rounded-lg" style={inputStyle()}>
              {CHANGE_TYPES.map(t => <option key={t} value={t}>{CHANGE_LABEL[t]}</option>)}
            </select>
            <input value={c.text} onChange={e => setChange(i, 'text', e.target.value)} placeholder="변경 내용"
              className="flex-1 px-3 py-1.5 text-xs rounded-lg" style={inputStyle()} />
            {changes.length > 1 && (
              <button onClick={() => removeChange(i)} className="text-[11px] px-1.5 py-1 rounded" style={{ color: '#f87171' }}>✕</button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
