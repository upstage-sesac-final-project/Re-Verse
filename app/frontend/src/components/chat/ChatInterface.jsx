import { useState, useEffect, useRef } from 'react'
import MessageList from './MessageList'
import PromptInput from './PromptInput'
import TypingIndicator from './TypingIndicator'
import SuggestedPrompts from './SuggestedPrompts'
import { sendPrompt } from '../../services/llmApi'
import { authFetch } from '../../services/api'

const MAX_STORED_MESSAGES = 50

export default function ChatInterface({ projectId, onGameUpdate, isCollapsed, onToggleCollapse }) {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [draft, setDraft] = useState('')
  const didFetchRef = useRef(null)

  // projectId 변경 시 백엔드에서 대화 기록 fetch
  useEffect(() => {
    if (!projectId) return
    // localStorage 캐시로 즉시 표시 (깜빡임 방지)
    try {
      const stored = localStorage.getItem(`chat_${projectId}`)
      if (stored) setMessages(JSON.parse(stored))
      else setMessages([])
    } catch { setMessages([]) }

    // 백엔드 API에서 실제 데이터 fetch → localStorage 덮어쓰기
    if (didFetchRef.current === projectId) return
    didFetchRef.current = projectId
    authFetch(`/v1/llm/history/${projectId}?limit=50`)
      .then(logs => {
        if (!Array.isArray(logs) || logs.length === 0) {
          // 백엔드에 기록 없으면 localStorage도 비움
          setMessages([])
          localStorage.removeItem(`chat_${projectId}`)
          return
        }
        const restored = []
        logs.reverse().forEach(log => {
          restored.push({ id: log.id * 2, role: 'user', content: log.user_input })
          if (log.agent_response) {
            restored.push({ id: log.id * 2 + 1, role: 'assistant', content: log.agent_response, intent: log.intent })
          }
        })
        setMessages(restored)
      })
      .catch(() => { /* localStorage 캐시 유지 */ })
  }, [projectId])

  // messages 변경 시 localStorage 캐시 갱신
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
      if (response.reload_required) onGameUpdate?.()
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
          <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>채팅</span>
        )}
        <div className="flex items-center gap-1 ml-auto">
          {!isCollapsed && messages.length > 0 && (
            <button
              onClick={() => {
                setMessages([])
                try { localStorage.removeItem(`chat_${projectId}`) } catch {}
              }}
              className="text-xs px-2 py-0.5 rounded transition-opacity hover:opacity-70"
              style={{ color: 'var(--text-secondary)' }}
            >
              초기화
            </button>
          )}
          <button
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? '패널 펼치기' : '패널 접기'}
            className="w-7 h-7 flex items-center justify-center rounded transition-opacity hover:opacity-70"
            style={{ color: 'var(--text-secondary)' }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {isCollapsed
                ? <polyline points="9 18 15 12 9 6" />
                : <polyline points="15 18 9 12 15 6" />
              }
            </svg>
          </button>
        </div>
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
