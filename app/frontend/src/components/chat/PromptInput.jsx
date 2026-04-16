import { useRef, useEffect } from 'react'

const MAX_LENGTH = 500

export default function PromptInput({ onSubmit, disabled, value, onChange }) {
  const textareaRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '40px'
    el.style.height = Math.min(el.scrollHeight, 150) + 'px'
  }, [value])

  function handleChange(e) {
    if (e.target.value.length <= MAX_LENGTH) onChange(e.target.value)
  }

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-3" style={{ borderTop: '1px solid var(--border)' }}>
      <div className="flex items-end gap-2">
        <textarea ref={textareaRef} value={value} onChange={handleChange} onKeyDown={handleKeyDown}
          placeholder="게임 요소를 설명하세요..." disabled={disabled} rows={1}
          className="flex-1 px-3 py-2 rounded-lg text-sm resize-none overflow-hidden focus:outline-none disabled:opacity-50"
          style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border)', minHeight: '40px', maxHeight: '150px' }}
        />
        <button type="submit" disabled={disabled || !value.trim()}
          className="w-8 h-8 flex items-center justify-center rounded-lg flex-shrink-0 disabled:opacity-30 transition-opacity"
          style={{ background: 'var(--accent)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>
      <div style={{ height: 16 }} className="flex items-center justify-end">
        {value.length > 0 && (
          <span className="text-[10px] tabular-nums" style={{ color: value.length >= MAX_LENGTH ? 'var(--accent)' : 'var(--text-secondary)' }}>
            {value.length}/{MAX_LENGTH}
          </span>
        )}
      </div>
    </form>
  )
}
