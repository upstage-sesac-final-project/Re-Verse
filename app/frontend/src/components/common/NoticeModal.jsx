import { useEffect, useState } from 'react'

const TYPE_BADGE = {
  new:     { label: 'NEW',  bg: 'rgba(34,197,94,0.12)',   color: '#4ade80' },
  fix:     { label: 'FIX',  bg: 'rgba(239,68,68,0.12)',   color: '#f87171' },
  improve: { label: '개선', bg: 'rgba(234,179,8,0.12)',   color: '#facc15' },
  remove:  { label: '제거', bg: 'rgba(142,142,147,0.12)', color: '#8e8e93' },
}

export default function NoticeModal({ onClose }) {
  const [tab, setTab] = useState('patch')
  const [patchNotes, setPatchNotes] = useState([])
  const [announcements, setAnnouncements] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/notices/patch-notes').then(r => r.ok ? r.json() : []),
      fetch('/api/v1/notices/announcements').then(r => r.ok ? r.json() : []),
      fetch('/api/v1/notices/latest-version').then(r => r.ok ? r.json() : null),
    ]).then(([patches, announces, latest]) => {
      setPatchNotes(patches)
      setAnnouncements(announces)
      if (latest?.version) {
        localStorage.setItem('re-verse:seen-version', latest.version)
      }
    }).catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative rounded-xl w-[520px] max-h-[80vh] flex flex-col shadow-xl"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>

        {/* 헤더 + 탭 */}
        <div className="flex-shrink-0 px-5 pt-5 pb-0">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>소식</h3>
            <button onClick={onClose} className="text-sm px-1" style={{ color: 'var(--text-secondary)' }}>✕</button>
          </div>
          <div className="flex gap-1" style={{ borderBottom: '1px solid var(--border)' }}>
            {[['patch', '패치노트'], ['announce', '공지사항']].map(([key, label]) => (
              <button key={key} onClick={() => setTab(key)}
                className="px-3 py-2 text-xs font-medium relative"
                style={{ color: tab === key ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                {label}
                {tab === key && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5" style={{ background: 'var(--accent)' }} />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* 콘텐츠 */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading
            ? <p className="text-xs text-center py-8" style={{ color: 'var(--text-secondary)' }}>로딩 중...</p>
            : tab === 'patch'
              ? <PatchTab items={patchNotes} />
              : <AnnounceTab items={announcements} />
          }
        </div>
      </div>
    </div>
  )
}

function PatchTab({ items }) {
  if (!items.length) return <p className="text-xs text-center py-8" style={{ color: 'var(--text-secondary)' }}>패치노트가 없습니다.</p>
  return (
    <div className="space-y-5">
      {items.map((patch) => (
        <div key={patch.id}>
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{patch.version}</span>
            <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>{patch.date}</span>
          </div>
          <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>{patch.title}</p>
          <div className="space-y-1.5">
            {patch.changes.map((c, i) => {
              const badge = TYPE_BADGE[c.type] || TYPE_BADGE.new
              return (
                <div key={i} className="flex items-start gap-2">
                  <span className="flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded mt-px"
                    style={{ background: badge.bg, color: badge.color }}>
                    {badge.label}
                  </span>
                  <span className="text-xs leading-relaxed" style={{ color: 'var(--text-primary)' }}>{c.text}</span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function AnnounceTab({ items }) {
  if (!items.length) return <p className="text-xs text-center py-8" style={{ color: 'var(--text-secondary)' }}>공지사항이 없습니다.</p>
  return (
    <div className="space-y-4">
      {items.map((item) => (
        <div key={item.id} className="rounded-lg p-3" style={{ background: 'var(--bg-primary)', border: item.pinned ? '1px solid rgba(255,59,92,0.2)' : '1px solid var(--border)' }}>
          <div className="flex items-center gap-2 mb-1.5">
            {item.pinned && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                style={{ background: 'rgba(255,59,92,0.12)', color: 'var(--accent)' }}>고정</span>
            )}
            <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{item.title}</span>
            <span className="text-[11px] ml-auto flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{item.date}</span>
          </div>
          <p className="text-xs leading-relaxed whitespace-pre-line" style={{ color: 'var(--text-secondary)' }}>{item.content}</p>
        </div>
      ))}
    </div>
  )
}
