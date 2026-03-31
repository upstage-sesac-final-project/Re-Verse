import { useState } from 'react'
import MessageList from './MessageList'
import PromptInput from './PromptInput'
import TypingIndicator from './TypingIndicator'
import { sendPrompt } from '../../services/llmApi'

export default function ChatInterface({ projectId, onGameUpdate, isCollapsed, onToggleCollapse }) {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(text) {
    const userMessage = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)

    const response = await sendPrompt(text, projectId)
    setMessages((prev) => [...prev, response])
    setIsLoading(false)

    onGameUpdate?.()
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
