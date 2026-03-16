import { useState } from 'react'
import MessageList from './MessageList'
import PromptInput from './PromptInput'
import { sendPrompt } from '../../services/llmApi'

export default function ChatInterface({ onGameUpdate }) {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(text) {
    const userMessage = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)

    const response = await sendPrompt(text, messages)
    setMessages((prev) => [...prev, response])
    setIsLoading(false)

    onGameUpdate?.()
  }

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="px-4 py-3 border-b border-gray-200 font-semibold text-gray-700">
        AI 프롬프트
      </div>
      <MessageList messages={messages} />
      <PromptInput onSubmit={handleSubmit} disabled={isLoading} />
    </div>
  )
}
