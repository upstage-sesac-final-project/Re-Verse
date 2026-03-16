import { post } from './api'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

const MOCK_RESPONSES = [
  '네, NPC를 생성해 드리겠습니다. 마을 입구에 상인 NPC를 배치했습니다.',
  '맵 데이터를 수정했습니다. 숲 타일을 추가하고 길을 연결했습니다.',
  '아이템 "불의 검"을 생성했습니다. 공격력 +15, 화염 속성이 부여되었습니다.',
  '이벤트를 설정했습니다. 플레이어가 해당 지점에 도달하면 대화가 시작됩니다.',
  '시나리오를 업데이트했습니다. 새로운 퀘스트 분기가 추가되었습니다.',
]

function getMockResponse() {
  return MOCK_RESPONSES[Math.floor(Math.random() * MOCK_RESPONSES.length)]
}

async function mockSendPrompt() {
  await new Promise((resolve) => setTimeout(resolve, 500))
  return { role: 'assistant', content: getMockResponse() }
}

/**
 * 사용자 프롬프트를 백엔드 LLM 엔드포인트로 전송
 * Backend: POST /api/v1/llm/process
 * Request: { request: string, game_id?: string, session_id?: string }
 * Response: { code, message, result, intent, modifications, affected_files }
 */
export async function sendPrompt(message, history) {
  if (USE_MOCK) {
    return mockSendPrompt()
  }

  try {
    const data = await post('/v1/llm/process', { request: message })
    return {
      role: 'assistant',
      content: data.message,
      intent: data.intent,
      modifications: data.modifications,
      affected_files: data.affected_files,
      result: data.result,
    }
  } catch (error) {
    console.error('LLM API 호출 실패:', error.message)
    return { role: 'assistant', content: `오류가 발생했습니다: ${error.message}` }
  }
}
