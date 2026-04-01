import { useState, useEffect } from 'react'
import MessageList from './MessageList'
import PromptInput from './PromptInput'
import TypingIndicator from './TypingIndicator'
import SuggestedPrompts from './SuggestedPrompts'
import { sendPrompt } from '../../services/llmApi'

const MAX_STORED_MESSAGES = 50

export default function ChatInterface({ projectId, onGameUpdate, isCollapsed, onToggleCollapse }) {
  const [messages, setMessages] = useState(() => {
    try {
      const stored = localStorage.getItem(`chat_${projectId}`)
      return stored ? JSON.parse(stored) : []
    } catch {
      return []
    }
  })
  const [isLoading, setIsLoading] = useState(false)
  const [draft, setDraft] = useState('')

  useEffect(() => {
    try {
      localStorage.setItem(`chat_${projectId}`, JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)))
    } catch {
      // localStorage quota exceeded — ignore
    }
  }, [messages, projectId])

  async function handleSubmit(text) {
    const id = Date.now()
    setDraft('')
    setMessages((prev) => [...prev, { id, role: 'user', content: text }])
    setIsLoading(true)

    try {
      const response = await sendPrompt(text, projectId)
      setMessages((prev) => [...prev, { id: id + 1, ...response }])
      onGameUpdate?.()
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: id + 1,
          role: 'assistant',
          content: `오류: ${err.message || '요청 처리 중 오류가 발생했습니다.'}`,
          retryInput: text,
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div
      className="flex flex-col h-full flex-shrink-0"
      style={{
        width: isCollapsed ? '48px' : '480px',
        transition: 'width 0.2s',
        background: '#232323',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* 패널 헤더 */}
      <div
        className="h-10 flex items-center justify-between px-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        {!isCollapsed && (
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            AI 어시스턴트
          </span>
        )}
        {!isCollapsed && messages.length > 0 && (
          <button
            onClick={() => {
              setMessages([])
              try { localStorage.removeItem(`chat_${projectId}`) } catch {}
            }}
            className="text-xs px-2 py-0.5 rounded hover:opacity-70 ml-auto mr-1"
            style={{ color: 'var(--text-secondary)' }}
            title="대화 기록 지우기"
          >
            지우기
          </button>
        )}
        <button
          onClick={onToggleCollapse}
          aria-label={isCollapsed ? '패널 펼치기' : '패널 접기'}
          className="w-7 h-7 flex items-center justify-center rounded text-sm hover:opacity-70"
          style={{ color: 'var(--text-secondary)' }}
        >
          {isCollapsed ? '▶' : '◀'}
        </button>
      </div>

      {!isCollapsed && (
        <>
          {messages.length === 0 ? (
            <SuggestedPrompts onSelect={(text) => setDraft(text)} />
          ) : (
            <MessageList messages={messages} onRetry={(text) => setDraft(text)} />
          )}
          {isLoading && (
            <div style={{ borderTop: '1px solid var(--border)' }}>
              <TypingIndicator />
            </div>
          )}
          <PromptInput onSubmit={handleSubmit} disabled={isLoading} value={draft} onChange={setDraft} />
        </>
      )}
    </div>
  )
}
