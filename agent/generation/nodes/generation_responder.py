"""J 노드 — generation_responder: 최종 사용자 메시지 생성.

canonical: docs/The_world/responder_node.md
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.J
"""

import logging

from agent.generation.models import GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


def _build_success_message(
    game_spec: GameSpec,
    id_table: IdTable,
    map_specs: list[MapSpec],
) -> str:
    actor_count = len(id_table.actors)
    item_count = len(id_table.items) + len(id_table.weapons) + len(id_table.armors)
    enemy_count = len(id_table.enemies)

    map_summary = []
    for mtype, label in [
        ("town", "마을"),
        ("dungeon", "던전"),
        ("boss", "보스 맵"),
        ("field", "필드"),
    ]:
        cnt = sum(1 for m in map_specs if m.map_type == mtype)
        if cnt:
            map_summary.append(f"{label} {cnt}개")

    synopsis = game_spec.story.get("synopsis", "") if isinstance(game_spec.story, dict) else ""
    synopsis_short = synopsis[:80] + ("..." if len(synopsis) > 80 else "")

    lines = [
        f"**{game_spec.title}** 게임이 생성되었습니다!",
        "",
        f"{synopsis_short}",
        "",
        "## 생성된 콘텐츠",
        f"- 캐릭터: {actor_count}명",
        f"- 맵: {len(map_specs)}개 ({', '.join(map_summary)})"
        if map_specs
        else f"- 에셋: {actor_count}명 생성",
        f"- 아이템/무기/방어구: {item_count}종",
        f"- 적 종류: {enemy_count}종",
        "",
        "RPG Maker MZ 에디터에서 바로 실행해보세요!",
    ]
    return "\n".join(lines)


def _build_partial_message(
    game_spec: GameSpec,
    errors: list[str],
    retry_count: int,
) -> str:
    lines = [
        f"**{game_spec.title}** 게임이 생성되었지만 일부 문제가 있습니다.",
        "",
        f"재시도 {retry_count}회 후에도 {len(errors)}개 오류가 남아있습니다.",
        "RPG Maker MZ에서 직접 확인하고 수정해주세요.",
        "",
        "## 알려진 문제",
    ]
    for err in errors[:5]:
        lines.append(f"- {err}")
    if len(errors) > 5:
        lines.append(f"- ... 외 {len(errors) - 5}개")
    return "\n".join(lines)


async def generation_responder(state: GenerationState) -> dict:
    """J 노드: 최종 메시지 생성 + WebSocket 100% 전송."""
    gen_id = state["generation_id"]

    # 가드레일 등에서 이미 실패 처리된 경우 (game_spec 없음)
    if state.get("is_success") is False and state.get("final_message"):
        logger.info(
            "generation_responder: 조기 종료 감지 (gen_id=%s) - %s",
            gen_id,
            state["final_message"],
        )
        # 에러 상태를 유지하며 100% 진행률 전송 (프론트엔드 실패 처리 유도)
        await publish_progress(
            gen_id,
            {
                "type": "error",
                "phase": state.get("error_phase", "unknown"),
                "progress": 100,
                "message": state["final_message"],
            },
        )
        return {}

    errors = state.get("validation_errors", [])
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs", [])
    retry_count = state.get("retry_count", 0)

    is_success = len(errors) == 0

    if is_success:
        message = _build_success_message(game_spec, id_table, map_specs)
    else:
        message = _build_partial_message(game_spec, errors, retry_count)

    logger.info(
        "generation_responder: gen_id=%s is_success=%s errors=%d",
        gen_id,
        is_success,
        len(errors),
    )

    await publish_progress(
        gen_id,
        {
            "type": "completed" if is_success else "completed_with_warnings",
            "progress": 100,
            "message": message,
        },
    )

    return {"final_message": message, "is_success": is_success}
