import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useSelector } from 'react-redux'
import { fetchDocs, saveDocs } from '../services/docsApi'

function renderContent(text) {
  // 간단한 마크다운 → HTML 렌더링
  return text
    .split('\n')
    .map((line, i) => {
      if (line.startsWith('## ')) return <h2 key={i} className="text-base font-semibold mt-5 mb-2" style={{ color: 'var(--text-primary)' }}>{line.slice(3)}</h2>
      if (line.startsWith('### ')) return <h3 key={i} className="text-sm font-semibold mt-4 mb-1" style={{ color: 'var(--text-primary)' }}>{line.slice(4)}</h3>
      if (line.startsWith('- ')) return <li key={i} className="ml-4 text-sm list-disc" style={{ color: 'var(--text-secondary)' }}>{renderInline(line.slice(2))}</li>
      if (line.startsWith('| ') && line.endsWith(' |')) return <TableRow key={i} line={line} />
      if (line.startsWith('|---')) return null
      if (line.startsWith('```')) return <div key={i} className="text-xs font-mono opacity-0 h-0" />
      if (line === '') return <div key={i} className="h-2" />
      return <p key={i} className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{renderInline(line)}</p>
    })
}

function renderInline(text) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="px-1 rounded text-xs font-mono" style={{ background: 'var(--border)', color: 'var(--accent)' }}>{part.slice(1, -1)}</code>
    }
    return part
  })
}

function TableRow({ line }) {
  const cells = line.split('|').filter((c) => c.trim() !== '')
  return (
    <div className="flex gap-0 text-sm border-b" style={{ borderColor: 'var(--border)' }}>
      {cells.map((c, i) => (
        <div key={i} className="flex-1 py-1 px-2" style={{ color: i === 0 ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
          {renderInline(c.trim())}
        </div>
      ))}
    </div>
  )
}

function CodeBlock({ lines }) {
  return (
    <pre className="rounded-lg p-3 text-xs font-mono my-2 overflow-x-auto" style={{ background: '#111', color: '#ccc' }}>
      {lines.join('\n')}
    </pre>
  )
}

function renderWithCode(text) {
  const lines = text.split('\n')
  const result = []
  let codeLines = null
  let key = 0

  for (const line of lines) {
    if (line.startsWith('```')) {
      if (codeLines === null) {
        codeLines = []
      } else {
        result.push(<CodeBlock key={key++} lines={codeLines} />)
        codeLines = null
      }
      continue
    }
    if (codeLines !== null) {
      codeLines.push(line)
      continue
    }
    const rendered = renderContent(line + '\n')
    if (rendered[0]) result.push(<div key={key++}>{rendered}</div>)
  }
  return result
}

export default function Docs() {
  const { user } = useSelector((s) => s.user)
  const isAdmin = user?.isAdmin

  const [sections, setSections] = useState([])
  const [activeKey, setActiveKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState('')
  const [editingKey, setEditingKey] = useState(null)
  const [editDraft, setEditDraft] = useState({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)
  const textareaRef = useRef(null)
  const handleSaveRef = useRef(null)

  useEffect(() => {
    fetchDocs()
      .then(({ sections: s }) => {
        setSections(s)
        if (s.length > 0) setActiveKey(s[0].key)
      })
      .catch((e) => setFetchError(e.message || '문서를 불러올 수 없습니다'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (editingKey && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [editingKey])

  useEffect(() => {
    function onKeyDown(e) {
      if (editingKey && (e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        handleSaveRef.current?.()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [editingKey])

  const activeSection = sections.find((s) => s.key === activeKey)

  function startEdit(section) {
    setEditDraft({ title: section.title, content: section.content })
    setEditingKey(section.key)
    setSaveError('')
  }

  function cancelEdit() {
    setEditingKey(null)
    setEditDraft({})
    setSaveError('')
  }

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    const updated = sections.map((s) =>
      s.key === editingKey ? { ...s, title: editDraft.title, content: editDraft.content } : s
    )
    try {
      const res = await saveDocs(updated)
      setSections(res.sections)
      setEditingKey(null)
      setEditDraft({})
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (e) {
      setSaveError(e.message || '저장에 실패했습니다')
    } finally {
      setSaving(false)
    }
  }

  handleSaveRef.current = handleSave

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* 헤더 */}
      <header
        className="h-14 flex items-center justify-between px-6 flex-shrink-0"
        style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}
      >
        <Link to="/" className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            R
          </div>
          <span className="font-semibold text-lg" style={{ color: 'var(--text-primary)' }}>
            Re:Verse
          </span>
          <span className="text-sm ml-1" style={{ color: 'var(--text-secondary)' }}>/ 사용자 가이드</span>
        </Link>
        <div className="flex gap-2">
          <Link
            to="/dashboard"
            className="text-xs px-3 py-1.5 rounded-lg"
            style={{ color: 'var(--text-secondary)' }}
          >
            대시보드
          </Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto flex gap-0 px-4 py-8">
        {/* 사이드바 */}
        <nav className="w-52 flex-shrink-0 mr-8">
          <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-secondary)' }}>
            목차
          </p>
          {loading
            ? Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-8 rounded mb-1 animate-pulse" style={{ background: 'var(--border)' }} />
              ))
            : sections.map((s) => (
                <button
                  key={s.key}
                  onClick={() => { setActiveKey(s.key); cancelEdit() }}
                  className="w-full text-left px-3 py-2 rounded-lg text-sm mb-0.5 transition-colors"
                  style={{
                    background: activeKey === s.key ? 'var(--accent)' + '22' : 'transparent',
                    color: activeKey === s.key ? 'var(--accent)' : 'var(--text-secondary)',
                    borderLeft: activeKey === s.key ? '2px solid var(--accent)' : '2px solid transparent',
                  }}
                >
                  {s.title}
                </button>
              ))}
        </nav>

        {/* 콘텐츠 */}
        <main className="flex-1 min-w-0">
          {loading && (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-4 rounded animate-pulse" style={{ background: 'var(--border)', width: `${60 + i * 5}%` }} />
              ))}
            </div>
          )}

          {!loading && activeSection && (
            <div
              className="rounded-xl p-6"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            >
              {/* 섹션 헤더 */}
              <div className="flex items-center justify-between mb-5">
                {editingKey === activeSection.key ? (
                  <input
                    className="text-xl font-bold bg-transparent border-b outline-none flex-1 mr-4"
                    style={{ color: 'var(--text-primary)', borderColor: 'var(--accent)' }}
                    value={editDraft.title}
                    onChange={(e) => setEditDraft((d) => ({ ...d, title: e.target.value }))}
                  />
                ) : (
                  <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
                    {activeSection.title}
                  </h1>
                )}

                {isAdmin && editingKey !== activeSection.key && (
                  <button
                    onClick={() => startEdit(activeSection)}
                    className="text-xs px-3 py-1.5 rounded-lg flex-shrink-0"
                    style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
                  >
                    편집
                  </button>
                )}
              </div>

              {/* 콘텐츠 편집 모드 */}
              {editingKey === activeSection.key ? (
                <div className="space-y-3">
                  <textarea
                    ref={textareaRef}
                    className="w-full rounded-lg p-3 text-sm font-mono resize-y outline-none"
                    style={{
                      background: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      border: '1px solid var(--border)',
                      minHeight: 360,
                    }}
                    value={editDraft.content}
                    onChange={(e) => setEditDraft((d) => ({ ...d, content: e.target.value }))}
                  />
                  {saveError && (
                    <p className="text-xs" style={{ color: '#f87171' }}>{saveError}</p>
                  )}
                  <div className="flex items-center gap-2 justify-end">
                    <span className="text-xs mr-auto" style={{ color: 'var(--text-secondary)' }}>
                      ⌘S로 저장
                    </span>
                    <button
                      onClick={cancelEdit}
                      className="text-xs px-3 py-1.5 rounded-lg"
                      style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
                    >
                      취소
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="text-xs px-4 py-1.5 rounded-lg font-medium disabled:opacity-50"
                      style={{ background: 'var(--accent)', color: '#fff' }}
                    >
                      {saving ? '저장 중...' : '저장'}
                    </button>
                  </div>
                </div>
              ) : (
                /* 콘텐츠 렌더링 모드 */
                <div className="space-y-0.5">
                  {renderWithCode(activeSection.content)}
                </div>
              )}
            </div>
          )}

          {!loading && fetchError && (
            <p className="text-sm" style={{ color: '#f87171' }}>{fetchError}</p>
          )}

          {!loading && !fetchError && !activeSection && (
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>섹션을 선택하세요.</p>
          )}
        </main>
      </div>

      {saveSuccess && (
        <div
          className="fixed bottom-5 right-5 px-4 py-3 rounded-lg text-sm font-medium shadow-lg"
          style={{ background: '#166534', color: '#bbf7d0', zIndex: 50 }}
        >
          저장되었습니다
        </div>
      )}
    </div>
  )
}
