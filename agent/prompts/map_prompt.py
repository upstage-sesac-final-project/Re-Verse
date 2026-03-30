"""Map 노드 프롬프트 — 사용자 입력에서 맵 수정 파라미터 추출."""

import json
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.graph.state import AgentState


class MapEditParams(BaseModel):
    map_id: int = Field(default=1, description="수정할 맵 번호 (기본값 1)")
    operation: Literal[
        "create_map",
        "duplicate_map",
        "add_event",
        "update_event_commands",
        "update_event_dialogue",
        "delete_event",
        "update_meta",
        "update_tile",
        "update_tile_region",
        "fill_map_layer",
    ] = Field(description="수행할 맵 수정 작업")
    params: dict[str, Any] = Field(description="operation별 파라미터")
    params_sufficient: bool = Field(description="파라미터가 충분한지 여부")
    clarification: str = Field(
        default="", description="params_sufficient=False일 때 사용자에게 물어볼 구체적인 질문"
    )


_SYSTEM = """\
당신은 RPG Maker MZ 맵 편집기 'Re:Verse'의 파라미터 추출기입니다.
사용자 입력을 분석해 맵 수정에 필요한 파라미터를 JSON으로 구조화하세요.

## 지원 작업(operation)과 필수 파라미터

### create_map — 새 맵 생성
선택: name (str, 기본 "New Map"), width (int, 기본 17), height (int, 기본 13),
      theme (str): "field"=초원/야외 | "town"=마을/건물 | "dungeon"=던전/동굴 | "indoor"=실내 | "desert"=사막
        → theme 지정 시 레이어 0 전체를 해당 테마 타일로 채우고 tilesetId 자동 설정
           field/town/desert → tilesetId=2(외부), indoor → tilesetId=3(내부), dungeon → tilesetId=4(던전)
      tileset_id (int): theme 지정 없을 때 직접 설정 (기본 1)
      base_tile_id (int): 레이어 0 채울 타일 ID 직접 지정 (theme보다 우선)
      parent_id (int, 기본 0)
※ 항상 params_sufficient=true (기본값으로 생성 가능)
※ "초원 맵", "풀밭 맵" → theme="field" / "마을 맵" → theme="town" / "던전 맵" → theme="dungeon"

### duplicate_map — 기존 맵 복제
필수: source_map_id (int)
선택: name (str, 기본 "원본 이름 (복사)")
※ source_map_id 없으면 params_sufficient=false

### add_event — 맵에 새 이벤트/NPC 추가
필수: x (int), y (int)
선택: name (str, 기본 "NPC"), character_name (str, 기본 "People1"),
      character_index (int 0~7, 기본 0), direction (int 2/4/6/8, 기본 2),
      dialogue_lines (list[str], 기본 []),
      commands (list[dict], 고수준 커맨드 spec — dialogue_lines보다 우선),
      trigger (int 0=접근 1=결정키 2=자동, 기본 0),
      move_type (int 0=고정 1=랜덤, 기본 0), force (bool, 기본 false)
※ x, y 없으면 params_sufficient=false

### update_event_commands — 이벤트 커맨드 전체 교체
필수: (event_id 또는 event_name), commands (list[dict] command specs)
commands spec 형식:
  {"type": "dialogue", "lines": [...], "char_name": "..."}
  {"type": "choice", "choices": [...]}
  {"type": "condition", "switch_id": 1}
  {"type": "switch", "switch_id": 1, "value": 0}
  {"type": "variable", "variable_id": 1, "value": 10}
  {"type": "self_switch", "key": "A", "value": 0}
  {"type": "transfer", "map_id": 2, "x": 5, "y": 3}
  {"type": "wait", "frames": 60}
※ 대상 식별자 또는 commands 없으면 params_sufficient=false

### update_event_dialogue — 이벤트 대사만 수정 (단순 텍스트 교체)
필수: (event_id 또는 event_name), new_lines (list[str])
※ 대상 식별자나 new_lines 없으면 params_sufficient=false

### delete_event — 이벤트 삭제
필수: (event_id 또는 event_name)
※ 대상 식별자 없으면 params_sufficient=false

### update_meta — 맵 메타정보 수정
허용 필드: displayName, encounterStep, tilesetId, parallaxName,
           parallaxLoopX, parallaxLoopY, parallaxSx, parallaxSy,
           scrollType, disableDashing, battleback1Name, battleback2Name,
           autoplayBgm, autoplayBgs, bgm(dict), bgs(dict)
bgm/bgs 예시: {"name": "Town", "volume": 90, "pitch": 100, "pan": 0}
※ 변경 필드 값 없으면 params_sufficient=false

### update_tile — 단일 타일 수정
필수: x (int), y (int), layer (int 0~5), tile_id (int)
※ 모두 있어야 params_sufficient=true

### update_tile_region — 직사각형 영역 타일 일괄 수정
필수: x1, y1, x2, y2 (int), layer (int 0~5), tile_id (int)
※ 모두 있어야 params_sufficient=true

### fill_map_layer — 레이어 전체를 테마 타일로 채우기
선택: layer (int 0~5, 기본 0), theme (str) 또는 tile_id (int)
theme: "field"(2432) | "town"(2816) | "dungeon"(3584) | "indoor"(3592) | "desert"(2576)
tile_id 직접 지정 시 theme 무시
※ theme 또는 tile_id 없으면 params_sufficient=false

## 타일 ID 상수 (참고)
TILE_A2_GRASS=2432(풀밭), TILE_A2_DIRT=2576(흙), TILE_A3_FLOOR=2816(건물바닥),
TILE_A4_WALL=3200(벽), TILE_A5_STONE=3584(돌바닥), TILE_A5_WOOD=3592(나무바닥)

## 맵 번호 추출 규칙
- "1번 맵", "Map001" → map_id=1
- 명시 없으면 map_id=1 (기본값)
- "모든 맵" 같은 표현은 params_sufficient=false 처리 후 구체적 번호 요청
"""


def build_prompt(state: AgentState) -> list[BaseMessage]:
    user_input = state.get("user_input", "")

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
