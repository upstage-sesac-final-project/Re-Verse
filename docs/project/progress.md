# Re:Verse 개발 현황 및 TODO

> 최종 업데이트: 2026-04-01
> 참고: 이 문서는 초기 구현 계획과 진행 기록이 섞여 있는 히스토리 문서다. 현재 구조 요약은 `docs/index.md`, 실행 방법은 `docs/project/setup.md`, validator 관련 최신 내용은 `docs/nodes/validator/` 아래 문서를 우선 본다.

---

## 전체 구조 한눈에 보기

```
Re-Verse/
├── app/backend/        # FastAPI 서버 (Python)
├── agent/              # LangGraph AI 에이전트 (Python)
├── app/frontend/       # React 18 + Vite (JavaScript)
├── shared/             # 백엔드↔에이전트 공유 타입 (미구현)
└── storage/games/      # RPG Maker MZ 게임 데이터 (JSON)
```

**데이터 흐름**
```
사용자 입력
  → [Frontend] React 채팅 UI
  → [Backend] POST /api/v1/llm/process
  → [Agent] LangGraph 워크플로우 (6개 노드)
  → storage/games/{game_id}/data/ JSON 파일 수정
  → Frontend 게임 뷰어 자동 갱신
```

---

## ✅ 구현 완료

### Backend

| 파일 | 내용 |
|------|------|
| `app/backend/main.py` | FastAPI 앱, CORS, `/game` 정적 파일 서빙, LangSmith 초기화 |
| `app/backend/core/config.py` | 환경변수 설정 (`.env` 로드) |
| `app/backend/api/v1/endpoints/llm.py` | `POST /api/v1/llm/process` 엔드포인트 |
| `app/backend/schemas/llm.py` | 요청/응답 Pydantic 스키마 |
| `app/backend/services/llm_service.py` | 키워드 기반 의도 분류 → 편집 함수 호출 (임시 구현, 추후 agent 그래프로 교체 예정) |
| `app/backend/services/json_modify_tools/` | 게임 JSON 직접 수정 도구 5종 (skills, items, enemies, levels, map_villager) |

### Agent

| 파일 | 내용 |
|------|------|
| `agent/core/config.py` | LLM 설정 (API 키, 모델, base_url) |
| `agent/core/llm_client.py` | LLM 호출 클라이언트. Solar·OpenAI·vLLM 등 OpenAI 호환 API 통합 지원 |
| `agent/graph/state.py` | 워크플로우 공유 상태 (`AgentState` TypedDict) |
| `agent/graph/workflow.py` | LangGraph StateGraph — 6개 노드 연결 및 조건부 라우팅 정의 |
| `agent/graph/routing.py` | 각 노드 이후 분기 로직 (route_after_router 등) |
| `agent/graph/nodes/*.py` | 6개 노드 파일 — 시그니처 및 import 구조 완성, 내부 구현은 TODO |
| `agent/prompts/*_prompt.py` | 6개 프롬프트 파일 — `build_prompt()` 구조 완성, 프롬프트 내용은 TODO |
| `agent/monitoring/langsmith_setup.py` | LangSmith 트레이싱 연동 |

### Frontend

| 파일 | 내용 |
|------|------|
| `app/frontend/src/pages/GameEditor.jsx` | 메인 에디터 (채팅 패널 + 게임 뷰어 분할 레이아웃) |
| `app/frontend/src/pages/Home.jsx` | 랜딩 페이지 |
| `app/frontend/src/components/chat/` | ChatInterface, MessageList, PromptInput |
| `app/frontend/src/components/game/RPGMakerFrame.jsx` | RPG Maker 게임 iframe 뷰어 |
| `app/frontend/src/services/api.js` | fetch 래퍼 (get/post) |
| `app/frontend/src/services/llmApi.js` | `/api/v1/llm/process` 호출 |

### 인프라

| 항목 | 상태 |
|------|------|
| Docker Compose (개발/프로덕션) | ✅ |
| GitHub Actions CI (lint, test) | ✅ |
| GitHub Actions CD (EC2 배포) | ✅ |
| Pre-commit hooks (ruff) | ✅ |
| `.env.example` | ✅ |

---

## 🔴 우선 구현 필요 (블로커)

> 이것들이 없으면 다른 작업을 해도 실제로 동작하지 않습니다.

### 1. Agent 그래프 ↔ Backend 연결
**파일:** `app/backend/services/llm_service.py`

현재 `llm_service.py`는 키워드 기반으로 동작합니다 (예: "스킬" 키워드 → edit_skills 호출).
LangGraph 그래프가 완성되면 이 부분을 아래처럼 교체해야 합니다.

```python
# 현재 (키워드 기반)
if "스킬" in user_input:
    tool_result = run_skills(user_input)

# 변경 후 (LangGraph 호출)
from agent.graph.workflow import graph
result = await graph.ainvoke({"user_input": user_input, "game_id": game_id})
final_response = result.get("final_response")
```

---

### 2. Router 노드 구현
**파일:** `agent/graph/nodes/router.py`, `agent/prompts/router_prompt.py`
**담당:** 세종

`AgentState`를 받아 의도를 분류하고 반환합니다.

```python
# 입력 (state에서 읽음)
state["user_input"]          # 사용자 입력 문자열
state["conversation_history"] # 이전 대화 목록

# 출력 (반환할 dict)
{
    "intent": "game_modify",   # game_create | game_modify | game_query | clarification_needed | ...
    "confidence": 0.92,
    "final_response": ""       # clarification 시에만 채움
}
```

`router_prompt.py`의 `build_prompt(state)`에 시스템 프롬프트를 작성하고,
`router.py`에서 `invoke_llm(messages, structured_output=_RouterOutput)`으로 호출하면 됩니다.

---

### 3. Definition 노드 구현
**파일:** `agent/graph/nodes/definition.py`, `agent/prompts/definition_prompt.py`
**담당:** 정민

사용자 요청에서 "어떤 파일의 어떤 ID를 수정할지" 추출합니다.

```python
# 입력
state["user_input"]   # 예: "슬라임 HP를 500으로 올려줘"
state["intent"]       # 예: "game_modify"
state["game_id"]      # 예: "game_001"

# 출력
{
    "target_files": ["Enemies.json"],
    "modifications": [{"type": "update", "target": "enemy", "params": {"enemy_id": 1, "params[0]": 500}}],
    "extracted_ids": {"enemy_id": 1},
    "params_sufficient": True
}
```

게임 JSON에서 실제 ID를 찾는 방법:
```python
import json
with open("storage/games/game_001/data/Enemies.json") as f:
    enemies = json.load(f)
# enemies[0]은 항상 null, enemies[1]부터 실제 데이터
```

---

### 4. Planner 노드 구현
**파일:** `agent/graph/nodes/planner.py`, `agent/prompts/planner_prompt.py`
**담당:** 화진

Definition 결과를 받아 실행 순서가 있는 명령셋을 만듭니다.

```python
# 입력
state["modifications"]   # Definition이 추출한 수정 내용
state["extracted_ids"]   # 실제 ID 매핑

# 출력
{
    "execution_plan": [
        {
            "step_id": 1,
            "tool_name": "edit_enemies",   # json_modify_tools 에 있는 함수명
            "params": {"enemy_id": 1, "hp": 500},
            "depends_on": [],
            "description": "슬라임 HP 500으로 변경"
        }
    ]
}
```

---

### 5. Executor 노드 구현
**파일:** `agent/graph/nodes/executor.py`
**담당:** 정철

Planner가 만든 실행 계획대로 실제 JSON 파일을 수정합니다.
`app/backend/services/json_modify_tools/` 에 있는 함수들을 호출하면 됩니다.

```python
# 입력
state["execution_plan"]  # Planner가 만든 명령셋
state["game_id"]         # 수정할 게임 ID

# 출력
{
    "modified_game_state": {"Enemies.json": [...]},  # 수정 후 데이터
    "current_game_state": {"Enemies.json": [...]},   # 수정 전 데이터 (Validator용)
    "changes_log": [{"step_id": 1, "tool_name": "...", "success": True}],
    "tool_results": [...]
}
```

---

### 6. Validator 노드 구현
**파일:** `agent/graph/nodes/validator.py`
**담당:** 예빈

수정된 JSON이 RPG Maker MZ 규격에 맞는지 검사합니다.
검증 실패 시 `routing.py`의 `route_after_validator`가 Executor로 재시도를 보냅니다 (최대 2회).

```python
# 입력
state["modified_game_state"]  # Executor가 수정한 데이터
state["current_game_state"]   # 수정 전 데이터

# 출력
{
    "validation_result": {
        "passed": True,          # False면 Executor 재시도
        "errors": [],            # 오류 목록
        "error_count": 0
    }
}
```

MVP의 검증 로직 참고 (세종에게 문의):
- 스키마 검증: JSON 필드/타입이 올바른지
- 참조 검증: 존재하지 않는 ID를 참조하는지
- diff 검증: 의도한 대로 수정이 됐는지

---

### 7. Synthesizer 노드 구현
**파일:** `agent/graph/nodes/synthesizer.py`, `agent/prompts/synthesizer_prompt.py`
**담당:** 세종

모든 처리 결과를 사용자가 이해할 수 있는 문장으로 변환합니다.

```python
# 입력
state["changes_log"]        # 어떤 작업이 성공/실패했는지
state["validation_result"]  # 검증 결과
state["user_input"]         # 원래 요청 (응답 문맥용)

# 출력
{"final_response": "슬라임의 HP를 500으로 성공적으로 변경했습니다."}
```

---

## 🟡 그 다음 구현 (기능 완성)

### 8. RAG 파이프라인
**파일:** `agent/rag/retriever.py`, `agent/rag/vectorstore.py`, `agent/rag/embeddings.py`

Definition 노드에서 사용할 지식 검색 시스템입니다.
예: "데미지 올려줘" → Trait Code 검색 → `{"code": 22, "dataId": 1}` 반환

### 9. RPG Maker Pydantic 스키마
**파일:** `app/backend/rpgmaker/schemas/`

MVP에 완성된 13개 스키마 파일이 있습니다 (세종에게 파일 받으세요).
`Validator` 노드가 이 스키마로 JSON을 검증합니다.

### 10. Redux 슬라이스
**파일:** `app/frontend/src/store/gameSlice.js`, `editorSlice.js`, `userSlice.js`

현재 프론트엔드는 로컬 state로만 동작합니다.
게임 상태, 채팅 이력, 현재 게임 ID 등을 전역으로 관리하려면 슬라이스 구현이 필요합니다.

---

## 📁 주요 파일 위치 빠른 참조

```
# 노드 구현 위치
agent/graph/nodes/{노드명}.py

# 프롬프트 작성 위치
agent/prompts/{노드명}_prompt.py

# LLM 호출 방법
from agent.core.llm_client import invoke_llm, invoke_llm_simple

# 게임 JSON 데이터 위치
storage/games/game_001/data/
  ├── Actors.json     # 플레이어 캐릭터
  ├── Enemies.json    # 적/몬스터
  ├── Skills.json     # 스킬
  ├── Items.json      # 아이템
  ├── Weapons.json    # 무기
  ├── Armors.json     # 방어구
  ├── Map001.json     # 맵 데이터
  └── System.json     # 게임 시스템 설정

# 환경변수 설정
.env  (루트 디렉토리, .env.example 참고)
```

---

## 🔧 로컬 개발 환경 세팅

```bash
# 1. 의존성 설치
uv sync --all-extras --dev

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에서 LLM_API_KEY 입력

# 3. 백엔드 실행
uv run uvicorn app.backend.main:app --reload

# 4. 프론트엔드 실행 (별도 터미널)
cd app/frontend
npm ci
npm run dev
```

> 자세한 설정은 `docs/project/setup.md` 참고
