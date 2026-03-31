import { useState } from 'react'
import MessageList from './MessageList'
import PromptInput from './PromptInput'
import TypingIndicator from './TypingIndicator'
import { sendPrompt } from '../../services/llmApi'

export default function ChatInterface({ projectId, onGameUpdate, isCollapsed, onToggleCollapse }) {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(text) {
    const id = Date.now()
    setMessages((prev) => [...prev, { id, role: 'user', content: text }])
    setIsLoading(true)

    try {
      const response = await sendPrompt(text, projectId)
      setMessages((prev) => [...prev, { id: id + 1, ...response }])
      onGameUpdate?.()
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: id + 1, role: 'assistant', content: `오류: ${err.message || '요청 처리 중 오류가 발생했습니다.'}` },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div
      className="flex flex-col h-full flex-shrink-0 transition-all duration-200"
      style={{
        width: isCollapsed ? '48px' : '480px',
        background: 'var(--bg-secondary)',
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
        <button
          onClick={onToggleCollapse}
          aria-label={isCollapsed ? '패널 펼치기' : '패널 접기'}
          className="ml-auto w-7 h-7 flex items-center justify-center rounded text-sm hover:opacity-70"
          style={{ color: 'var(--text-secondary)' }}
        >
          {isCollapsed ? '▶' : '◀'}
        </button>
      </div>

      {!isCollapsed && (
        <>
          <MessageList messages={messages} />
          {isLoading && (
            <div style={{ borderTop: '1px solid var(--border)' }}>
              <TypingIndicator />
            </div>
          )}
          <PromptInput onSubmit={handleSubmit} disabled={isLoading} />
        </>
      )}
    </div>
  )
}
