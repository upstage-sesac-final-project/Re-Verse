# MVP → Re-Verse 기능 이식 계획

## Context
`claude_Re-Verse/` MVP에서 완성된 LangGraph 워크플로우 프레임, 검증 엔진, Pydantic 스키마, 툴 레지스트리, LLM 클라이언트를 현재 Re-Verse 구조(`app/backend/`, `agent/`, `app/frontend/` 분리)에 이식한다. 프론트엔드는 기존 React 18 + Vite 유지. 백엔드는 키워드 기반 라우팅 → LangGraph 워크플로우로 교체.

---

## 마이그레이션 맵

| MVP 소스 | Re-Verse 대상 | 비고 |
|---------|-------------|------|
| `app/graph/workflow.py` | `agent/workflows/workflow.py` | import 경로 수정 |
| `app/graph/nodes/*.py` (11개) | `agent/workflows/nodes/*.py` | import 경로 수정 |
| `app/graph/routing.py` | `agent/workflows/routing.py` | |
| `app/models/state.py` | `agent/workflows/state.py` | |
| `app/services/llm.py` | `agent/core/llm_client.py` | `LLM_API_KEY` → `UPSTAGE_API_KEY` |
| `app/prompts/*.py` (10개) | `agent/prompts/` | import 경로 수정 |
| `app/validation/*.py` (3개) | `app/backend/rpgmaker/validation/` | 새 디렉토리 |
| `app/schemas/*.py` (16개) | `app/backend/rpgmaker/schemas/` | 기존 빈 dir 채움 |
| `app/tool_registry/` | `app/backend/services/tool_registry/` | 새 디렉토리, 경로 수정 |

---

## 단계별 작업

### 1단계: 의존성 추가
**파일:** `pyproject.toml`
- [ ] `langchain-upstage>=0.3.0` 추가 (현재 없음)

### 2단계: agent/core — LLM 클라이언트
**파일:** `agent/core/llm_client.py`, `agent/core/config.py`
- [ ] MVP `app/services/llm.py` → `agent/core/llm_client.py` 로 복사
- [ ] import: `from app.config import settings` → `from app.backend.core.config import settings`
- [ ] 환경변수: `settings.LLM_API_KEY` → `settings.UPSTAGE_API_KEY`
- [ ] `agent/core/config.py`에 agent 레이어용 설정 추가 (model name, timeout 등)

### 3단계: agent/workflows — LangGraph 프레임
**파일:** `agent/workflows/`
- [ ] `state.py`: MVP `app/models/state.py` 복사 (경로 독립적)
- [ ] `workflow.py`: MVP `app/graph/workflow.py` 복사, import 경로 수정
  - `from app.graph.nodes.*` → `from agent.workflows.nodes.*`
  - `from app.graph.routing` → `from agent.workflows.routing`
  - `from app.models.state` → `from agent.workflows.state`
- [ ] `routing.py`: MVP `app/graph/routing.py` 복사, import 수정
- [ ] `nodes/__init__.py`, `nodes/*.py` (11개): 각 노드 파일 복사, import 수정
  - `from app.services.llm` → `from agent.core.llm_client`
  - `from app.config` → `from app.backend.core.config`
  - `from app.tool_registry` → `from app.backend.services.tool_registry`
  - `from app.validation` → `from app.backend.rpgmaker.validation`
  - `from app.schemas` → `from app.backend.rpgmaker.schemas`

### 4단계: agent/prompts — 프롬프트 템플릿
**파일:** `agent/prompts/` (기존 빈 dir)
- [ ] MVP `app/prompts/*.py` 10개 파일 복사
- [ ] `from app.prompts.utils` → `from agent.prompts.utils`

### 5단계: app/backend/rpgmaker/schemas — Pydantic 스키마
**파일:** `app/backend/rpgmaker/schemas/` (기존 빈 dir)
- [ ] MVP `app/schemas/*.py` 16개 파일 복사 (경로 독립적, 수정 최소)

### 6단계: app/backend/rpgmaker/validation — 검증 엔진
**파일:** `app/backend/rpgmaker/validation/` (새 디렉토리)
- [ ] MVP `app/validation/*.py` 3개 파일 복사
- [ ] `schema_validator.py`: `from app.schemas` → `from app.backend.rpgmaker.schemas`
- [ ] `reference_checker.py`, `diff_checker.py`: import 경로 수정

### 7단계: app/backend/services/tool_registry — 툴 레지스트리
**파일:** `app/backend/services/tool_registry/` (새 디렉토리)
- [ ] MVP `app/tool_registry/` 전체 복사
- [ ] `file_handler.py`: `from app.config import settings` → `from app.backend.core.config import settings`
  - `settings.game_data_path` → game_id 기반 경로 함수로 교체 (`storage/games/{game_id}/data/`)
- [ ] `tools/*.py`: `from app.config` → `from app.backend.core.config`

### 8단계: app/backend/services/llm_service.py 교체
**파일:** `app/backend/services/llm_service.py`
- [ ] 키워드 기반 `_call_agent()` → LangGraph 워크플로우 호출로 교체
- [ ] `from agent.workflows.workflow import graph` import
- [ ] `graph.ainvoke({"user_input": ..., "conversation_history": ...})` 호출
- [ ] 결과에서 `final_response`, `changes_log`, `intent` 추출하여 `AgentResponse` 반환

### 9단계: config 보완
**파일:** `app/backend/core/config.py`
- [ ] `game_data_path(game_id: str)` 메서드 추가
  ```python
  def game_data_path(self, game_id: str) -> str:
      return f"{self.STORAGE_PATH}/{game_id}/data"
  ```

---

## 핵심 import 변경 패턴

```python
# MVP → Re-Verse
from app.config import settings           → from app.backend.core.config import settings
from app.services.llm import invoke_llm   → from agent.core.llm_client import invoke_llm
from app.models.state import AgentState   → from agent.workflows.state import AgentState
from app.graph.nodes import ...           → from agent.workflows.nodes import ...
from app.graph.routing import ...         → from agent.workflows.routing import ...
from app.schemas import ...               → from app.backend.rpgmaker.schemas import ...
from app.validation import ...            → from app.backend.rpgmaker.validation import ...
from app.tool_registry import ...         → from app.backend.services.tool_registry import ...
from app.prompts import ...               → from agent.prompts import ...
```

---

## 검증 방법

1. `uv sync --all-extras --dev` — 의존성 설치 확인
2. `uv run ruff check .` — lint 오류 없음 확인
3. `uv run uvicorn app.backend.main:app --reload` — 서버 기동 확인
4. `POST /api/v1/llm/process` 에 `{"request": "슬라임 HP를 100으로 올려줘", "game_id": "game_001"}` 테스트
5. `GET /game/game_001` — 게임 파일 서빙 확인

---

## 작업 범위 외

- 프론트엔드 변경 없음
- Supabase 연동 없음
- RAG 파이프라인 구현 없음 (agent/rag/ 스텁 유지)
- game_designer / game_executor 노드는 스텁으로 유지 가능
