import logging

from agent.core.llm_client import invoke_llm
from agent.generation.prompts.game_designer_prompt import build_game_designer_prompt
from agent.generation.schemas import GameSpec
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def game_designer_node(state: GenerationState) -> GenerationState:
    """A. 기획자 노드: 유저 입력을 바탕으로 GameSpec 생성."""
    logger.info("--- NODE: game_designer ---")
    user_input = state["user_input"]

    # TODO: publish_progress 연동 필요

    for attempt in range(3):
        try:
            # structured_output=GameSpec을 사용하여 직접 파싱 시도
            messages = build_game_designer_prompt(user_input)
            spec = await invoke_llm(messages, structured_output=GameSpec)

            if not isinstance(spec, GameSpec):
                raise ValueError("GameSpec 파싱 결과가 올바르지 않습니다.")

            # 맵 연결성 검증
            _validate_map_connections(spec)

            # 최종 맵 개수 강제 제한 (안전 장치)
            if len(spec.maps) > 3:
                logger.warning(
                    f"기획된 맵이 {len(spec.maps)}개로 너무 많습니다. 상위 3개로 제한합니다."
                )
                spec.maps = spec.maps[:3]

            logger.info("GameSpec 생성 성공: %s", spec.title)
            return {
                **state,
                "game_spec": spec.model_dump(),
                "completed_phases": ["spec"],
                "current_phase": "spec",
            }

        except Exception as e:
            logger.warning("GameSpec 생성 실패 (시도 %d/3): %s", attempt + 1, e)
            continue

    raise RuntimeError("게임 기획 생성에 실패했습니다 (3회 시도 초과).")


def _validate_map_connections(spec: GameSpec) -> None:
    """모든 맵이 시작 맵에서 도달 가능한지 BFS로 확인하고, 고립된 맵은 자동으로 연결한다."""
    if not spec.maps:
        raise ValueError("생성된 맵이 없습니다.")

    map_names = {m.name for m in spec.maps}
    # 양방향 그래프로 가정 (갈 수 있으면 올 수 있음)
    graph: dict[str, set[str]] = {m.name: set(m.connects_to) for m in spec.maps}
    # 역방향 연결도 추가 (도달 가능성 확보를 위해)
    for m in spec.maps:
        for target in m.connects_to:
            if target in graph:
                graph[target].add(m.name)

    start_name = spec.maps[0].name
    visited = set()
    queue = [start_name]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if current in graph:
            queue.extend(graph[current] & map_names)

    unreachable = map_names - visited
    if unreachable:
        logger.warning(f"고립된 맵 발견: {unreachable}. 시작 맵({start_name})에 강제로 연결합니다.")
        # 시작 맵의 connects_to에 고립된 맵들을 추가하여 연결성 확보
        for m in spec.maps:
            if m.name == start_name:
                for target_name in unreachable:
                    if target_name not in m.connects_to:
                        m.connects_to.append(target_name)
                break
