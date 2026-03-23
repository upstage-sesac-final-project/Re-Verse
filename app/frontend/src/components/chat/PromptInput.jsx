import { useRef } from 'react'

export default function PromptInput({ onSubmit, disabled }) {
  const textareaRef = useRef(null)

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 150) + 'px'
  }

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = textareaRef.current?.value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    textareaRef.current.value = ''
    textareaRef.current.style.height = 'auto'
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex gap-2 p-3"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      <textarea
        ref={textareaRef}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="게임 요소를 자연어로 설명하세요..."
        disabled={disabled}
        rows={1}
        className="flex-1 px-3 py-2 rounded-lg text-sm resize-none overflow-hidden focus:outline-none disabled:opacity-50"
        style={{
          background: 'var(--bg-primary)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border)',
          minHeight: '40px',
          maxHeight: '150px',
        }}
      />
      <button
        type="submit"
        disabled={disabled}
        className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
        style={{ background: 'var(--accent)' }}
      >
        전송
      </button>
    </form>
  )
}
