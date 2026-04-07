import asyncio
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from agent.generation.compilers.dsl_models import DslEventList
from agent.generation.schemas import MapSpec
from agent.generation.state import GenerationState
from agent.utils.game_data_io import save_temp_data

logger = logging.getLogger(__name__)


async def event_planner_node(state: GenerationState) -> GenerationState:
    """F. 이벤트 기획자 노드: 각 맵별로 이벤트를 DSL 형태로 설계."""
    logger.info("--- NODE: event_planner ---")
    map_specs = state.get("map_specs", [])
    game_spec = state.get("game_spec")
    id_table = state.get("id_table")
    game_id = state["game_id"]

    if game_spec is None or id_table is None:
        raise ValueError("game_spec or id_table is missing in state")

    tasks = []
    for spec_dict in map_specs:
        spec = MapSpec.model_validate(spec_dict)
        tasks.append(_plan_events_for_map(spec, game_spec, id_table))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 이벤트 DSL 결과를 맵 ID별로 정리 (mypy 에러 방지를 위해 타입 명시)
    for spec_dict, result in zip(map_specs, results):
        m_id = int(spec_dict["map_id"])
        dsl_data: list[Any] = []
        if isinstance(result, list):
            dsl_data = result
        elif isinstance(result, Exception):
            logger.error("Map %d 이벤트 설계 실패: %s", m_id, result)

        # 파일로 저장 (Pointer 방식)
        save_temp_data(game_id, "dsl", m_id, dsl_data)

    return {
        **state,
        "event_dsl": {},  # 상태 다이어트
        "completed_phases": state.get("completed_phases", []) + ["events_planned"],
        "current_phase": "events_planned",
    }


async def _plan_events_for_map(
    map_spec: MapSpec, game_spec: dict[Any, Any], id_table: dict[Any, Any]
) -> list[dict[Any, Any]]:
    system_prompt = """\
당신은 RPG Maker MZ 이벤트 기획자입니다.
맵 명세와 게임 기획을 바탕으로 해당 맵에 배치할 이벤트를 YAML DSL로 작성하세요.

## 지원하는 이벤트 타입
- npc: 대화형 NPC
- transfer: 맵 이동
- shop: 상점
- chest: 보물 상자
- battle: 전투

## 규칙
- 모든 이름(맵, 아이템, 스위치 등)은 반드시 제공된 ID 테이블에 있는 이름을 사용하세요.
- 좌표(x, y)는 맵 크기 내에 있어야 합니다.
- npc 이벤트의 character_name은 아래 목록 중 하나를 선택하세요 (맵에서 보이는 스프라이트):
  일반/판타지: People1, People2, People3, People4, Actor1, Actor2, Actor3, Monster, Evil
  SF/현대: SF_People1, SF_People2, SF_People3, SF_Actor1, SF_Actor2, SF_Monster
- character_index: 0~7 (같은 시트 안의 위치, NPC마다 다른 값으로 다양성 확보)
"""
    human_prompt = f"""\
## 맵 명세
{map_spec.model_dump()}

## 게임 기획 및 ID 테이블
{game_spec.get("title", "Game")} / {game_spec.get("theme", "Fantasy")}
아이템: {list(id_table.get("items", {}).keys())[:20]}
맵 목록: {list(id_table.get("maps", {1: "Map"}).keys())}

YAML 형식으로 'events:' 리스트를 작성하세요.
"""

    for attempt in range(2):
        try:
            # DslEventList 스키마를 사용하여 구조화된 출력 시도
            result = await invoke_llm(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ],
                structured_output=DslEventList,
            )
            if isinstance(result, DslEventList):
                return [e.model_dump() for e in result.events]
            return []
        except Exception as e:
            logger.warning("이벤트 설계 실패 (시도 %d/2): %s", attempt + 1, e)

    return []
