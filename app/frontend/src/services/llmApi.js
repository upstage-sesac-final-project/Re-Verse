import { authFetch } from './api'

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

const MOCK_CHANGES = [
  [
    { step_id: 1, tool_name: 'edit_enemies', description: '슬라임 HP 수정', success: true, result_summary: 'hp: 100 → 500' },
  ],
  [
    { step_id: 1, tool_name: 'edit_skills', description: '파이어볼 데미지 수정', success: true, result_summary: 'damage: 50 → 120' },
    { step_id: 2, tool_name: 'edit_items', description: 'MP 포션 효과 수정', success: false, result_summary: '대상 아이템을 찾을 수 없음' },
  ],
  [],
]

async function mockSendPrompt() {
  await new Promise((resolve) => setTimeout(resolve, 500))
  const changes = MOCK_CHANGES[Math.floor(Math.random() * MOCK_CHANGES.length)]
  return { role: 'assistant', content: getMockResponse(), changes_log: changes }
}

/**
 * 사용자 프롬프트를 백엔드 LLM 엔드포인트로 전송
 * Backend: POST /api/v1/llm/process
 * Request: { project_id: string, message: string }
 */
export async function sendPrompt(message, projectId, history) {
  if (USE_MOCK) {
    return mockSendPrompt()
  }

  try {
    const data = await authFetch('/v1/llm/process', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, message }),
    })
    return {
      role: 'assistant',
      content: data.message,
      intent: data.intent,
      modifications: data.modifications,
      affected_files: data.affected_files,
      result: data.result,
      changes_log: data.changes_log ?? [],
    }
  } catch (error) {
    console.error('LLM API 호출 실패:', error.message)
    return { role: 'assistant', content: `오류가 발생했습니다: ${error.message}` }
  }
}
