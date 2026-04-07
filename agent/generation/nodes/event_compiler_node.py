import logging
from typing import Any

from pydantic import TypeAdapter

from agent.generation.compilers.dsl_models import DslEvent
from agent.generation.compilers.event_compiler import EventCompiler
from agent.generation.state import GenerationState
from agent.utils.game_data_io import save_temp_data

logger = logging.getLogger(__name__)

# 성능 최적화: 어댑터를 한 번만 생성
dsl_adapter: TypeAdapter[DslEvent] = TypeAdapter(DslEvent)


async def event_compiler_node(state: GenerationState) -> GenerationState:
    """G. 이벤트 컴파일러 노드: DSL 이벤트를 RPG Maker MZ 커맨드로 변환."""
    logger.info("--- NODE: event_compiler ---")
    event_dsl_dict = state.get("event_dsl", {})
    id_table = state.get("id_table")
    switch_table = state.get("switch_table")
    game_id = state["game_id"]

    if id_table is None or switch_table is None:
        raise ValueError("id_table or switch_table is missing in state")

    compiler = EventCompiler(id_table, switch_table)

    for map_id_key, dsl_list in event_dsl_dict.items():
        compiled_list: list[Any] = []
        map_id_str = str(map_id_key)

        for dsl_data in dsl_list:
            try:
                # DslEvent 유니온 모델로 파싱
                dsl_event = dsl_adapter.validate_python(dsl_data)
                compiled_event = compiler.compile_event(dsl_event)
                if compiled_event:
                    compiled_list.append(compiled_event)
            except Exception as e:
                event_name = (
                    dsl_data.get("name", "Unknown") if isinstance(dsl_data, dict) else "N/A"
                )
                logger.error(f"이벤트 컴파일 오류 (Map {map_id_str}, {event_name}): {e}")

        # [핵심] 컴파일된 결과를 파일로 저장
        save_temp_data(game_id, "events", map_id_str, compiled_list)

    logger.info(f"이벤트 컴파일 완료: {len(event_dsl_dict)}개 맵 처리됨")

    return {
        **state,
        "compiled_events": {},  # 상태 다이어트 — 실제 데이터는 temp 파일로 저장됨
        "completed_phases": state.get("completed_phases", []) + ["events_compiled"],
        "current_phase": "events_compiled",
    }
