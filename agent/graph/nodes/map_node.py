"""Map 노드 — 맵 이벤트/타일/메타정보 수정 전담 노드."""

import logging

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.map_editor.dispatcher import execute_map_operation
from agent.prompts.map_prompt import MapEditParams, build_prompt

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

    # 4. 결과를 state에 기록
    validation_errors = result.get("validation_errors", [])
    error_msg = result.get("error")

    errors_combined = []
    if error_msg:
        errors_combined.append(error_msg)
    errors_combined.extend(validation_errors)

    update: dict = {
        "success": result["success"],
        "validation_results": [
            {
                "file": f"Map{parsed.map_id:03d}.json",
                "passed": result["success"],
                "errors": errors_combined,
                "error_count": len(errors_combined),
            }
        ],
        "validation_summary": (
            f"맵 수정 {'성공' if result['success'] else '실패'}: {parsed.operation}"
            + (f" — {error_msg}" if error_msg else "")
        ),
        "tool_results": [result],
    }

    if result["success"]:
        update["changes_log"] = result["changes"]

    return update
