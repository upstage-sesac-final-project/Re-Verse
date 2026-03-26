"""Map 노드 프롬프트 — 사용자 입력에서 맵 수정 파라미터 추출."""

import json
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.graph.state import AgentState

# ── Structured Output 스키마 ──────────────────────────────────────────────────


class MapEditParams(BaseModel):
    map_id: int = Field(default=1, description="수정할 맵 번호 (기본값 1)")
    operation: Literal[
        "add_event",
        "update_event_dialogue",
        "delete_event",
        "update_meta",
        "update_tile",
        "update_tile_region",
    ] = Field(description="수행할 맵 수정 작업")
    params: dict[str, Any] = Field(description="operation별 파라미터")
    params_sufficient: bool = Field(description="파라미터가 충분한지 여부")
    clarification: str = Field(
        default="", description="params_sufficient=False일 때 사용자에게 물어볼 구체적인 질문"
    )


# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

_SYSTEM = """\
당신은 RPG Maker MZ 맵 편집기 'Re:Verse'의 파라미터 추출기입니다.
사용자 입력을 분석해 맵 수정에 필요한 파라미터를 JSON으로 구조화하세요.

## 지원하는 작업(operation)과 필수 파라미터

### add_event — 맵에 새 이벤트/NPC 추가
필수: x (int), y (int)
선택: name (str, 기본 "NPC"), character_name (str, 기본 "People1"),
      character_index (int 0~7, 기본 0), direction (int 2/4/6/8, 기본 2),
      dialogue_lines (list[str], 기본 []),
      trigger (int 0=접근 1=결정키 2=자동, 기본 0),
      move_type (int 0=고정 1=랜덤, 기본 0), force (bool 좌표 덮어쓰기, 기본 false)
※ x, y가 없으면 params_sufficient=false

### update_event_dialogue — 이벤트 대사 수정
필수: (event_id 또는 event_name), new_lines (list[str])
※ 대상 식별자나 새 대사가 없으면 params_sufficient=false

### delete_event — 이벤트 삭제
필수: (event_id 또는 event_name)
※ 대상 식별자가 없으면 params_sufficient=false

### update_meta — 맵 메타정보 수정
허용 필드: displayName, encounterStep, tilesetId, parallaxName,
           parallaxLoopX, parallaxLoopY, parallaxSx, parallaxSy,
           scrollType, disableDashing, battleback1Name, battleback2Name,
           autoplayBgm, autoplayBgs, bgm(dict), bgs(dict)
bgm/bgs 예시: {"name": "Town", "volume": 90, "pitch": 100, "pan": 0}
※ 변경할 필드 값이 없으면 params_sufficient=false

### update_tile — 단일 타일 수정
필수: x (int), y (int), layer (int 0~3), tile_id (int)
※ 모두 있어야 params_sufficient=true

### update_tile_region — 직사각형 영역 타일 일괄 수정
필수: x1, y1, x2, y2 (int), layer (int 0~3), tile_id (int)
※ 모두 있어야 params_sufficient=true

## 파라미터 충분 여부 판단
- params_sufficient=true: 작업 수행에 필요한 최소 파라미터가 모두 있음
- params_sufficient=false: 핵심 파라미터 누락 → clarification 필드에 무엇이 필요한지 질문 작성

## 맵 번호 추출 규칙
- "1번 맵", "Map001", "마을 맵(Map001)" → map_id=1
- 명시 없으면 map_id=1 (기본값)
- "모든 맵" 같은 표현은 params_sufficient=false 처리 후 구체적 번호 요청\
"""


# ── 프롬프트 빌더 ─────────────────────────────────────────────────────────────


def build_prompt(state: AgentState) -> list[BaseMessage]:
    user_input = state.get("user_input", "")

    # 현재 맵 데이터가 있으면 컨텍스트로 제공
    game_context = state.get("game_context") or {}
    context_text = ""
    if game_context:
        context_text = "\n\n## 현재 맵 컨텍스트\n" + json.dumps(
            game_context, ensure_ascii=False, indent=2
        )

    human_content = f"## 사용자 입력\n{user_input}{context_text}"

    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=human_content),
    ]
