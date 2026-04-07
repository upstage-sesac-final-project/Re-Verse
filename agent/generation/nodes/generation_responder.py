import logging

from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState
from agent.utils.game_data_io import cleanup_temp_data

logger = logging.getLogger(__name__)


async def generation_responder_node(state: GenerationState) -> GenerationState:
    """J. 응답기 노드: 사용자에게 최종 결과 메시지 생성 및 전송."""
    logger.info("--- NODE: generation_responder ---")

    is_success = state.get("validation_passed", False)
    game_spec = state.get("game_spec") or {}
    errors = state.get("validation_errors", [])
    game_id = state["game_id"]

    title = game_spec.get("title", "게임") if isinstance(game_spec, dict) else "게임"
    if is_success:
        msg = f"**{title}** 생성이 완료되었습니다! 🎮\nRPG Maker MZ에서 바로 확인해보세요."

    else:
        msg = "게임 생성 중 일부 문제가 발생했습니다.\n오류 목록:\n" + "\n".join(
            [f"- {e}" for e in errors]
        )

    # [핵심] 생성 완료 후 임시 데이터 정리
    cleanup_temp_data(game_id)

    await publish_progress(
        state["generation_id"],
        {"type": "completed" if is_success else "failed", "progress": 100, "message": msg},
    )

    return {**state, "final_message": msg, "is_success": is_success, "current_phase": "completed"}
