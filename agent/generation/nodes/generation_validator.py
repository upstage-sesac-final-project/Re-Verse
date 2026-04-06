"""I 노드 — generation_validator: RPG Maker MZ 프로젝트 검증.

Phase 2: 에셋 관련 검증만 (R1, null-at-0, array lengths).
Phase 3+에서 맵/이벤트 검증 추가.
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.I
canonical: docs/The_world/risks_and_mitigations.md
"""

import logging

from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

MAX_RETRY = 2


def _check_null_at_index_0(final_project: dict) -> list[str]:
    """모든 배열 파일의 index-0이 null인지 검증."""
    errors = []
    array_files = [
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "Troops.json",
        "States.json",
        "Animations.json",
        "CommonEvents.json",
    ]
    for fname in array_files:
        data = final_project.get(fname)
        if data is None:
            continue
        if not isinstance(data, list):
            errors.append(f"[R_NULL] {fname}: 배열이 아님")
            continue
        if len(data) == 0 or data[0] is not None:
            errors.append(
                f"[R_NULL] {fname}: index-0이 null이 아님 (값={data[0] if data else 'empty'})"
            )
    return errors


def _check_id_references(final_project: dict, id_table: IdTable) -> list[str]:
    """Actors.json의 classId가 Classes.json에 존재하는지 검증 (R1)."""
    errors = []
    actors = final_project.get("Actors.json", [])
    classes = final_project.get("Classes.json", [])

    valid_class_ids = {c["id"] for c in classes if c is not None}

    for actor in actors:
        if actor is None:
            continue
        cid = actor.get("classId", 0)
        if cid not in valid_class_ids:
            errors.append(f"[R1] Actors.json: {actor.get('name', '?')} classId={cid} 미존재")

    return errors


def _check_array_lengths(final_project: dict) -> list[str]:
    """Classes.json params[i]가 99개인지 검증."""
    errors = []
    classes = final_project.get("Classes.json", [])
    for cls in classes:
        if cls is None:
            continue
        params = cls.get("params", [])
        if len(params) != 8:
            errors.append(
                f"Classes.json: {cls.get('name', '?')} params 행 수={len(params)} (기대:8)"
            )
            continue
        for i, row in enumerate(params):
            if len(row) != 99:
                errors.append(
                    f"Classes.json: {cls.get('name', '?')} params[{i}] 길이={len(row)} (기대:99)"
                )
    return errors


async def generation_validator(state: GenerationState) -> dict:
    """I 노드: 생성된 프로젝트 파일 검증."""
    gen_id = state["generation_id"]
    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "validation",
            "progress": 94,
            "message": "검증 중...",
        },
    )

    final_project: dict = state.get("final_project", {})
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    retry_count: int = state.get("retry_count", 0)

    errors: list[str] = []
    warnings: list[str] = []

    # 검증 실행
    errors.extend(_check_null_at_index_0(final_project))
    errors.extend(_check_id_references(final_project, id_table))
    errors.extend(_check_array_lengths(final_project))

    validation_passed = len(errors) == 0

    if errors:
        logger.warning("generation_validator: %d 오류 발견 (retry=%d)", len(errors), retry_count)
        for err in errors:
            logger.warning("  %s", err)
    else:
        logger.info("generation_validator: 검증 통과")

    if warnings:
        await publish_progress(
            gen_id,
            {
                "type": "warning",
                "category": "validation",
                "warnings": warnings,
            },
        )

    completed = list(state.get("completed_phases", []))
    completed.append("validation")
    return {
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "retry_count": retry_count + (0 if validation_passed else 1),
        "completed_phases": completed,
    }


def route_after_validation(state: GenerationState) -> str:
    """validator 이후 라우팅 결정."""
    errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)

    if not errors:
        return "respond"
    if retry_count >= MAX_RETRY:
        return "respond"

    # 오류 태그별 재시도 라우트
    tags = {err.split("]")[0].lstrip("[") for err in errors if "]" in err}
    if "R1" in tags or "R_NULL" in tags:
        return "retry_assets"

    return "respond"
