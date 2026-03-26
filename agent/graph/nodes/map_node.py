"""Map 노드 — 맵 이벤트/타일/메타정보 수정 전담 노드.

담당: 세종님
"""

import logging

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.map_prompt import MapEditParams, build_prompt
from app.backend.services.map_editor.dispatcher import execute_map_operation

logger = logging.getLogger(__name__)


async def map_node(state: AgentState) -> dict:
    user_input = state.get("user_input", "")
    game_id = state.get("game_id", "game_001")

    logger.info("Map 노드 시작: user_input=%r", user_input)

    # 1. LLM으로 맵 수정 파라미터 추출
    messages = build_prompt(state)
    parsed: MapEditParams = await invoke_llm(messages, structured_output=MapEditParams)  # type: ignore[assignment]

    logger.info(
        "Map 파라미터 추출: operation=%s, map_id=%d, sufficient=%s",
        parsed.operation,
        parsed.map_id,
        parsed.params_sufficient,
    )

    # 2. 파라미터 불충분 → 사용자에게 재질문
    if not parsed.params_sufficient:
        return {
            "final_response": parsed.clarification or "맵 수정에 필요한 정보를 더 알려주세요.",
        }

    # 3. 맵 수정 실행
    result = execute_map_operation(
        game_id=game_id,
        map_id=parsed.map_id,
        operation=parsed.operation,
        params=parsed.params,
    )

    logger.info(
        "Map 수정 결과: success=%s, error=%s",
        result["success"],
        result.get("error"),
    )

    # 4. 결과를 state에 기록 (synthesizer가 final_response 생성)
    update: dict = {
        "tool_results": [result],
        "validation_result": {
            "passed": result["success"],
            "errors": [result["error"]] if result.get("error") else [],
            "error_count": 0 if result["success"] else 1,
        },
    }

    if result["success"]:
        update["changes_log"] = result["changes"]

    return update
