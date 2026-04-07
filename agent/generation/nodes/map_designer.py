import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from agent.core.llm_client import invoke_llm
from agent.generation.schemas import MapSpec
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


class MapSpecList(BaseModel):
    items: list[MapSpec]


async def map_designer_node(state: GenerationState) -> GenerationState:
    """D. 맵 설계사 노드: GameSpec을 바탕으로 각 맵의 상세 명세(MapSpec) 생성."""
    logger.info("--- NODE: map_designer ---")
    game_spec = state.get("game_spec")
    id_table = state.get("id_table")

    if game_spec is None or id_table is None:
        raise ValueError("game_spec or id_table is missing in state")

    system_prompt = """\
당신은 RPG Maker MZ 맵 설계사입니다.
게임 기획서를 바탕으로 각 맵의 상세 명세(MapSpec)를 JSON으로 작성하세요.

## 맵 타입별 설정 규칙
- town: width=30, height=30, tileset_id=1, bgm="Town1"
- dungeon: width=40, height=30, tileset_id=2, bgm="Dungeon1"
- boss: width=20, height=20, tileset_id=2, bgm="Battle1"
- field: width=40, height=30, tileset_id=1, bgm="Field1"

## 연결 규칙
- 각 맵은 연결된 다른 맵으로의 exits를 1개 이상 가져야 합니다 (고립 금지).
- to_map_id는 id_table에 정의된 맵 ID를 사용하세요.
"""

    human_prompt = f"""\
## 게임 기획서
{game_spec}

## 맵 ID 정보 (id_table)
{id_table.get("maps", {})}

모든 맵에 대한 MapSpec 리스트를 생성하세요.
"""

    for attempt in range(3):
        try:
            # invoke_llm에 SystemMessage, HumanMessage 객체 전달
            result = await invoke_llm(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ],
                structured_output=MapSpecList,
            )

            # result가 MapSpecList 모델인 경우 .items 속성 사용
            if isinstance(result, MapSpecList):
                map_specs = result.items
                logger.info("MapSpec 생성 성공: %d개 맵", len(map_specs))

                return {
                    **state,
                    "map_specs": [m.model_dump() for m in map_specs],
                    "completed_phases": state.get("completed_phases", []) + ["maps_designed"],
                    "current_phase": "maps_designed",
                }
            else:
                raise ValueError("Unexpected result type from invoke_llm")

        except Exception as e:
            logger.warning("MapSpec 생성 실패 (시도 %d/3): %s", attempt + 1, e)

    raise RuntimeError("맵 설계 생성에 실패했습니다.")
