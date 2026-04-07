"""GenerationValidator 노드 — 생성된 JSON 파일 검증 (LLM 없음)."""

import json
import logging

from agent.generation.state import GenerationState
from app.backend.core.game_paths import get_game_data_path

logger = logging.getLogger(__name__)

VALID_FACE_FILES = {"Actor1", "Actor2", "Actor3", "People1", "Evil"}
VALID_ENEMY_BATTLERS = {
    "Bat",
    "Bee",
    "Berserker",
    "Captain",
    "Cockatrice",
    "Darklord",
    "Dragon",
    "Gargoyle",
    "Ghost",
    "Goblin",
    "Hornet",
    "Lamia",
    "Minotaur",
    "Orc",
    "Rat",
    "Sahagin",
    "Skeleton",
    "Slime",
    "Snake",
    "Spider",
    "Vampire",
    "Werewolf",
    "Willowisp",
    "Zombie",
}
VALID_SV_ACTORS = {
    "Actor1_1",
    "Actor1_2",
    "Actor1_3",
    "Actor2_1",
    "Actor2_2",
    "Actor2_3",
}


async def generation_validator(state: GenerationState) -> dict:
    """생성된 JSON 파일들을 검증한다."""
    game_id = state["game_id"]
    build_errors = state.get("build_errors", [])
    retry_count = state.get("retry_count", 0)

    logger.info("[Validator] 시작: game_id=%s, retry=%d", game_id, retry_count)

    # 빌드 오류가 있으면 즉시 실패
    if build_errors:
        logger.error("[Validator] 빌드 오류: %s", build_errors)
        return {
            "success": False,
            "validation_results": [
                {"check": "build_errors", "ok": False, "detail": str(build_errors)}
            ],
            "validation_summary": f"빌드 오류: {build_errors}",
            "retry_count": retry_count + 1,
        }

    data_path = get_game_data_path(game_id)
    results = []

    # 필수 파일 존재 확인
    required_files = [
        "System.json",
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "Troops.json",
    ]
    for fname in required_files:
        path = data_path / fname
        if path.exists():
            results.append({"check": f"{fname} 존재", "ok": True})
        else:
            results.append({"check": f"{fname} 존재", "ok": False, "detail": f"{fname} 없음"})

    # JSON 파싱 및 배열[0]=null 확인
    array_files = [
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "Troops.json",
    ]
    loaded: dict[str, list] = {}
    for fname in array_files:
        path = data_path / fname
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                results.append({"check": f"{fname} 배열 형식", "ok": False})
                continue
            loaded[fname] = data
            ok = data[0] is None if data else False
            results.append(
                {"check": f"{fname}[0]=null", "ok": ok, "detail": None if ok else f"[0]={data[0]}"}
            )
        except Exception as e:
            results.append({"check": f"{fname} 파싱", "ok": False, "detail": str(e)})

    # id == 배열 인덱스 확인
    for fname, data in loaded.items():
        mismatches = []
        for idx, item in enumerate(data):
            if item is None:
                continue
            if item.get("id") != idx:
                mismatches.append(f"idx={idx}, id={item.get('id')}")
        ok = len(mismatches) == 0
        results.append(
            {
                "check": f"{fname} id=인덱스",
                "ok": ok,
                "detail": mismatches[:3] if not ok else None,
            }
        )

    # Actor.classId 참조 유효성
    if "Actors.json" in loaded and "Classes.json" in loaded:
        class_ids = {item["id"] for item in loaded["Classes.json"] if item is not None}
        invalid = []
        for actor in loaded["Actors.json"]:
            if actor is None:
                continue
            if actor.get("classId", 0) not in class_ids:
                invalid.append(f"{actor['name']}.classId={actor.get('classId')}")
        ok = len(invalid) == 0
        results.append(
            {"check": "Actor.classId 참조", "ok": ok, "detail": invalid[:3] if not ok else None}
        )

    # Actor.equips 5개 확인
    if "Actors.json" in loaded:
        bad = [a["name"] for a in loaded["Actors.json"] if a and len(a.get("equips", [])) != 5]
        ok = len(bad) == 0
        results.append({"check": "Actor.equips 5개", "ok": ok, "detail": bad if not ok else None})

    # Enemy.dropItems 3개 확인
    if "Enemies.json" in loaded:
        bad = [e["name"] for e in loaded["Enemies.json"] if e and len(e.get("dropItems", [])) != 3]
        ok = len(bad) == 0
        results.append(
            {"check": "Enemy.dropItems 3개", "ok": ok, "detail": bad if not ok else None}
        )

    # 리소스 파일명 확인
    if "Actors.json" in loaded:
        for actor in loaded["Actors.json"]:
            if actor is None:
                continue
            face_ok = actor.get("faceName", "") in VALID_FACE_FILES
            sv_ok = actor.get("battlerName", "") in VALID_SV_ACTORS
            results.append({"check": f"{actor['name']}.faceName", "ok": face_ok})
            results.append({"check": f"{actor['name']}.battlerName(sv)", "ok": sv_ok})

    if "Enemies.json" in loaded:
        for enemy in loaded["Enemies.json"]:
            if enemy is None:
                continue
            ok = enemy.get("battlerName", "") in VALID_ENEMY_BATTLERS
            results.append({"check": f"{enemy['name']}.battlerName", "ok": ok})

    # 종합 판정
    failed = [r for r in results if not r.get("ok")]
    success = len(failed) == 0
    summary = (
        "검증 통과"
        if success
        else f"검증 실패 {len(failed)}건: " + "; ".join(r["check"] for r in failed[:5])
    )

    logger.info("[Validator] 결과: success=%s, failed=%d건", success, len(failed))

    return {
        "success": success,
        "validation_results": results,
        "validation_summary": summary,
        "retry_count": retry_count + 1,
    }
