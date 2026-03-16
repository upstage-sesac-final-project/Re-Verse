import json
import sys
from pathlib import Path
from typing import Any, TypedDict


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _actors_path() -> Path:
    return _project_root() / "storage" / "games" / "game_001" / "data" / "Actors.json"


def _classes_path() -> Path:
    return _project_root() / "storage" / "games" / "game_001" / "data" / "Classes.json"


def _skills_path() -> Path:
    return _project_root() / "storage" / "games" / "game_001" / "data" / "Skills.json"


def _system_path() -> Path:
    return _project_root() / "storage" / "games" / "game_001" / "data" / "System.json"


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _dump_rmmz_array_json(path: Path, data: list[Any], newline: str) -> None:
    lines: list[str] = ["["]
    for i, entry in enumerate(data):
        s = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        if i != len(data) - 1:
            s += ","
        lines.append(s)
    lines.append("]")
    path.write_text(newline.join(lines) + newline, encoding="utf-8")


def _dump_rmmz_object_json(path: Path, obj: Any, newline: str) -> None:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(s + newline, encoding="utf-8")


def _load_array_json(path: Path) -> tuple[list[Any], str]:
    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    data = json.loads(raw)
    if not isinstance(data, list) or not data or data[0] is not None:
        raise ValueError(f"Unexpected format: {path.name} (expected [null, ...])")
    return data, newline


def _load_object_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected format: {path.name} (expected object)")
    return data, newline


def _find_entry_by_name(arr: list[Any], name: str) -> int | None:
    for idx in range(1, len(arr)):
        e = arr[idx]
        if isinstance(e, dict) and (e.get("name") or "") == name:
            return idx
    return None


def _find_first_empty_name_slot(arr: list[Any]) -> int | None:
    for idx in range(1, len(arr)):
        e = arr[idx]
        if isinstance(e, dict) and (e.get("name") or "") == "":
            return idx
    return None


# ──────────────────────────────────────────────────────────────
# 스킬 프리셋 타입 정의
# ──────────────────────────────────────────────────────────────


class SkillEffect(TypedDict):
    code: int
    dataId: int
    value1: int
    value2: int


class SkillPreset(TypedDict):
    name: str
    description: str
    formula: str
    iconIndex: int
    message1: str
    stypeId: int
    stypeLabel: str
    mpCost: int
    scope: int
    damageType: int
    effects: list[SkillEffect]


# ──────────────────────────────────────────────────────────────
# 스킬 프리셋 정의
# ──────────────────────────────────────────────────────────────

SKILL_PRESETS: dict[str, SkillPreset] = {
    "최후의일격": {
        "name": "최후의 일격",
        "description": "단일 적에게 9999의 고정 피해를 준다.",
        "formula": "9999",
        "iconIndex": 76,
        "message1": "%1의 최후의 일격!",
        "stypeId": 5,
        "stypeLabel": "필살기",
        "mpCost": 0,
        "scope": 1,
        "damageType": 1,
        "effects": [],
    },
    "전체공격": {
        "name": "전체 공격",
        "description": "모든 적에게 500의 고정 피해를 준다.",
        "formula": "500",
        "iconIndex": 77,
        "message1": "%1의 전체 공격!",
        "stypeId": 5,
        "stypeLabel": "필살기",
        "mpCost": 30,
        "scope": 2,
        "damageType": 1,
        "effects": [],
    },
    "회복마법": {
        "name": "강력한 회복",
        "description": "아군 전체의 HP를 1000 회복한다.",
        "formula": "0",
        "iconIndex": 72,
        "message1": "%1의 강력한 회복!",
        "stypeId": 2,
        "stypeLabel": "마법",
        "mpCost": 50,
        "scope": 7,
        "damageType": 0,
        "effects": [{"code": 11, "dataId": 0, "value1": 1000, "value2": 0}],
    },
    "버프": {
        "name": "공격력 강화",
        "description": "아군 전체의 공격력을 50% 증가시킨다.",
        "formula": "0",
        "iconIndex": 32,
        "message1": "%1의 공격력 강화!",
        "stypeId": 2,
        "stypeLabel": "마법",
        "mpCost": 40,
        "scope": 7,
        "damageType": 0,
        "effects": [{"code": 31, "dataId": 2, "value1": 5, "value2": 50}],
    },
}


def _make_skill(skill_id: int, preset_key: str) -> dict[str, Any]:
    """프리셋을 기반으로 스킬 생성"""
    preset = SKILL_PRESETS[preset_key]

    return {
        "id": skill_id,
        "animationId": -1,
        "damage": {
            "critical": False,
            "elementId": 0,
            "formula": preset["formula"],
            "type": preset["damageType"],
            "variance": 0,
        },
        "description": preset["description"],
        "effects": preset["effects"],
        "hitType": 1,
        "iconIndex": preset["iconIndex"],
        "message1": preset["message1"],
        "message2": "",
        "mpCost": preset["mpCost"],
        "name": preset["name"],
        "note": "",
        "occasion": 1,
        "repeats": 1,
        "requiredWtypeId1": 0,
        "requiredWtypeId2": 0,
        "scope": preset["scope"],
        "speed": 0,
        "stypeId": preset["stypeId"],
        "successRate": 100,
        "tpCost": 0,
        "tpGain": 0,
        "messageType": 1,
    }


def _upsert_skill(skills: list[Any], name: str, preset_key: str) -> int:
    """스킬 추가 또는 업데이트"""
    existing_idx = _find_entry_by_name(skills, name)
    if existing_idx is not None:
        skills[existing_idx] = _make_skill(existing_idx, preset_key)
        return existing_idx

    empty_idx = _find_first_empty_name_slot(skills)
    if empty_idx is not None:
        skills[empty_idx] = _make_skill(empty_idx, preset_key)
        return empty_idx

    new_id = len(skills)
    skills.append(_make_skill(new_id, preset_key))
    return new_id


def _get_actor(actors: list[Any], actor_id: int) -> dict[str, Any]:
    if actor_id <= 0 or actor_id >= len(actors) or not isinstance(actors[actor_id], dict):
        raise ValueError(f"Actor not found: id={actor_id}")
    return actors[actor_id]


def _get_class(classes: list[Any], class_id: int) -> dict[str, Any]:
    if class_id <= 0 or class_id >= len(classes) or not isinstance(classes[class_id], dict):
        raise ValueError(f"Class not found: id={class_id}")
    return classes[class_id]


def _ensure_system_skill_type(system: dict[str, Any], stype_id: int, label: str) -> None:
    skill_types = system.get("skillTypes")
    if not isinstance(skill_types, list):
        raise ValueError("System.skillTypes is missing or invalid")

    while len(skill_types) <= stype_id:
        skill_types.append("")
    if (skill_types[stype_id] or "") == "":
        skill_types[stype_id] = label


def _ensure_class_has_skill_type(cl: dict[str, Any], stype_id: int) -> None:
    traits = cl.get("traits")
    if not isinstance(traits, list):
        raise ValueError("Class.traits is missing or invalid")
    for t in traits:
        if isinstance(t, dict) and t.get("code") == 41 and t.get("dataId") == stype_id:
            return
    traits.append({"code": 41, "dataId": stype_id, "value": 1})


def _ensure_class_learns_skill_at_level_one(cl: dict[str, Any], skill_id: int) -> None:
    learnings = cl.get("learnings")
    if not isinstance(learnings, list):
        raise ValueError("Class.learnings is missing or invalid")
    for i in learnings:
        if isinstance(i, dict) and i.get("skillId") == skill_id:
            if i.get("level") != 1:
                i["level"] = 1
            if "note" not in i:
                i["note"] = ""
            return
    learnings.append({"level": 1, "note": "", "skillId": skill_id})


def main(argv: list[str]) -> int:
    """
    Actor1에게 스킬을 추가

    Usage:
        python edit_skills.py [skill_type]
        python edit_skills.py                # 기본값: 최후의일격
        python edit_skills.py 최후의일격
        python edit_skills.py 전체공격
        python edit_skills.py 회복마법
        python edit_skills.py 버프
    """
    # 인자가 없으면 기본값 사용
    if len(argv) == 0:
        skill_type = "최후의일격"
    elif len(argv) == 1:
        skill_type = argv[0].strip()
        if skill_type not in SKILL_PRESETS:
            print(f"Unknown skill: {skill_type}", file=sys.stderr)
            print(f"Available skills: {', '.join(SKILL_PRESETS.keys())}", file=sys.stderr)
            return 2
    else:
        print("Usage: python edit_skills.py [skill_type]", file=sys.stderr)
        print(f"Available skills: {', '.join(SKILL_PRESETS.keys())}", file=sys.stderr)
        return 2

    for p in (_actors_path(), _classes_path(), _skills_path(), _system_path()):
        if not p.exists():
            print(f"Missing file: {p}", file=sys.stderr)
            return 2

    actors, actors_nl = _load_array_json(_actors_path())
    classes, classes_nl = _load_array_json(_classes_path())
    skills, skills_nl = _load_array_json(_skills_path())
    system, system_nl = _load_object_json(_system_path())

    lead = _get_actor(actors, 1)
    class_id = int(lead.get("classId") or 0)
    if class_id <= 0:
        print("Actor1 has no valid classId.", file=sys.stderr)
        return 2
    cl = _get_class(classes, class_id)

    preset = SKILL_PRESETS[skill_type]
    skill_id = _upsert_skill(skills, preset["name"], skill_type)
    _ensure_system_skill_type(system, preset["stypeId"], preset["stypeLabel"])
    _ensure_class_has_skill_type(cl, preset["stypeId"])
    _ensure_class_learns_skill_at_level_one(cl, skill_id)

    _dump_rmmz_array_json(_skills_path(), skills, skills_nl)
    _dump_rmmz_object_json(_system_path(), system, system_nl)
    _dump_rmmz_array_json(_classes_path(), classes, classes_nl)

    actor_name = str(lead.get("name") or "Actor1")
    class_name = str(cl.get("name") or f"Class{class_id}")
    print(
        f'OK: Added/updated skill "{preset["name"]}" (id={skill_id}, stypeId={preset["stypeId"]}) '
        f"and assigned to actor1 ({actor_name}) via class {class_id} ({class_name})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
