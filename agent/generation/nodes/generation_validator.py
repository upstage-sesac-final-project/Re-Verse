import logging
import os

from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def generation_validator_node(state: GenerationState) -> GenerationState:
    """I. 검증기 노드: 조립된 프로젝트의 물리적 파일 무결성 검증."""
    logger.info("--- NODE: generation_validator ---")
    game_id = state["game_id"]
    data_path = os.path.join("storage", "games", game_id, "data")

    errors = []

    # 1. 필수 파일 존재 확인
    required = ["System.json", "Actors.json", "Classes.json", "MapInfos.json"]
    if not os.path.exists(data_path):
        errors.append(f"데이터 폴더가 존재하지 않음: {data_path}")
    else:
        for req in required:
            file_path = os.path.join(data_path, req)
            if not os.path.exists(file_path):
                errors.append(f"필수 파일 누락: {req}")
            elif os.path.getsize(file_path) < 10:  # 너무 작은 파일(빈 파일 등) 체크
                errors.append(f"파일이 손상되었거나 비어있음: {req}")

        # 2. 맵 파일 확인
        files = os.listdir(data_path)
        map_files = [
            f for f in files if f.startswith("Map") and f[3:6].isdigit() and f.endswith(".json")
        ]
        if not map_files:
            errors.append("생성된 맵 파일(MapXXX.json)이 없습니다.")

    passed = len(errors) == 0
    if not passed:
        logger.warning(f"검증 실패: {errors}")
    else:
        logger.info("검증 통과!")

    return {
        **state,
        "validation_passed": passed,
        "validation_errors": errors,
        "completed_phases": ["validated"],
        "current_phase": "validated",
    }
