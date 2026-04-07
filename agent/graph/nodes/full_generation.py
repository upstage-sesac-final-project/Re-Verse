import logging
import uuid

from agent.generation.state import GenerationState
from agent.generation.workflow import generation_workflow
from agent.graph.state import AgentState
from agent.utils.game_data_io import setup_game_directory

logger = logging.getLogger(__name__)


async def full_generation(state: AgentState) -> AgentState:
    """메인 워크플로우에서 세계관 컴파일러(Full Generation)를 호출하는 브릿지 노드."""
    logger.info("--- NODE: full_generation ---")

    user_input = state["user_input"]
    game_id = state.get("game_id", f"game_{uuid.uuid4().hex[:7]}")
    gen_id = f"gen_{uuid.uuid4().hex[:7]}"

    # 0. 베이스 게임 디렉토리 준비 (에셋 및 엔진 파일 복사)
    try:
        setup_game_directory(game_id)
    except Exception as e:
        logger.error(f"게임 디렉토리 준비 실패: {e}")
        # 계속 진행 시도

    # 1. 초기 상태 구성
    initial_gen_state = GenerationState(
        user_input=user_input,
        game_id=game_id,
        generation_id=gen_id,
        completed_phases=[],
        retry_count=0,
    )

    # 2. 세계관 컴파일러 워크플로우 실행
    try:
        final_gen_state = await generation_workflow.ainvoke(initial_gen_state)

        # 3. 결과 반영
        return {
            **state,
            "game_id": game_id,
            "final_response": final_gen_state.get("final_message", "게임 생성이 완료되었습니다."),
            "success": final_gen_state.get("is_success", False),
        }
    except Exception as e:
        import traceback

        error_detail = traceback.format_exc()
        logger.error(f"세계관 컴파일러 실행 중 치명적 오류: {e}\n{error_detail}")
        return {
            **state,
            "game_id": game_id,
            "final_response": f"게임 세계관 생성 중 오류가 발생했습니다: {str(e) or type(e).__name__}",
            "success": False,
        }
