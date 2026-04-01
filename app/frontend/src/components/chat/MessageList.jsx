import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import ChangesBadge from './ChangesBadge'

export default function MessageList({ messages, onRetry }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-sm"
        style={{ color: 'var(--text-secondary)' }}
      >
        프롬프트를 입력하여 게임 요소를 생성하세요
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex items-end gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
            style={{
              background: msg.role === 'user' ? 'var(--accent)' : 'var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            {msg.role === 'user' ? 'U' : 'AI'}
          </div>
          <div
            className="max-w-[80%] px-3 py-2 rounded-lg text-sm"
            style={{
              background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg-primary)',
              color: 'var(--text-primary)',
              border: msg.role === 'assistant' ? '1px solid var(--border)' : 'none',
            }}
          >
            {msg.role === 'user' ? (
              <span className="whitespace-pre-wrap">{msg.content}</span>
            ) : (
              <div className="prose-sm" style={{ color: 'var(--text-primary)' }}>
                <ReactMarkdown
                  components={{
                    p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
                    strong: ({ children }) => (
                      <strong style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                        {children}
                      </strong>
                    ),
                    code: ({ children }) => (
                      <code
                        className="px-1 rounded text-xs"
                        style={{ background: 'var(--border)', color: '#a8d8a8' }}
                      >
                        {children}
                      </code>
                    ),
                    ul: ({ children }) => <ul className="list-disc pl-4 mb-1">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-4 mb-1">{children}</ol>,
                    li: ({ children }) => <li className="mb-0.5">{children}</li>,
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              </div>
            )}
            {msg.role === 'assistant' && <ChangesBadge changes={msg.changes_log} />}
            {msg.retryInput && onRetry && (
              <button
                onClick={() => onRetry(msg.retryInput)}
                className="mt-2 text-xs hover:opacity-80"
                style={{ color: 'var(--accent)' }}
              >
                다시 시도 →
              </button>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
