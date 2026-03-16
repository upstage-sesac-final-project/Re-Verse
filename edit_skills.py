import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _actors_path() -> Path:
    return _project_root() / "data" / "Actors.json"


def _classes_path() -> Path:
    return _project_root() / "data" / "Classes.json"


def _skills_path() -> Path:
    return _project_root() / "data" / "Skills.json"


def _system_path() -> Path:
    return _project_root() / "data" / "System.json"


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _dump_rmmz_array_json(path: Path, data: List[Any], newline: str) -> None:
    lines: List[str] = ["["]
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


def _load_array_json(path: Path) -> Tuple[List[Any], str]:
    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    data = json.loads(raw)
    if not isinstance(data, list) or not data or data[0] is not None:
        raise ValueError(f"Unexpected format: {path.name} (expected [null, ...])")
    return data, newline


def _load_object_json(path: Path) -> Tuple[Dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected format: {path.name} (expected object)")
    return data, newline


def _find_entry_by_name(arr: List[Any], name: str) -> Optional[int]:
    for idx in range(1, len(arr)):
        e = arr[idx]
        if isinstance(e, dict) and (e.get("name") or "") == name:
            return idx
    return None


def _find_first_empty_name_slot(arr: List[Any]) -> Optional[int]:
    for idx in range(1, len(arr)):
        e = arr[idx]
        if isinstance(e, dict) and (e.get("name") or "") == "":
            return idx
    return None


def _make_final_strike_skill(skill_id: int) -> Dict[str, Any]:
    return {
        "id": skill_id,
        "animationId": -1,
        "damage": {
            "critical": False,
            "elementId": 0,
            "formula": "9999",
            "type": 1,
            "variance": 0,
        },
        "description": "단일 적에게 9999의 고정 피해를 준다.",
        "effects": [],
        "hitType": 1,
        "iconIndex": 76,
        "message1": "%1의 최후의 일격!",
        "message2": "",
        "mpCost": 0,
        "name": "최후의 일격",
        "note": "",
        "occasion": 1,
        "repeats": 1,
        "requiredWtypeId1": 0,
        "requiredWtypeId2": 0,
        "scope": 1,
        "speed": 0,
        "stypeId": 5,
        "successRate": 100,
        "tpCost": 0,
        "tpGain": 0,
        "messageType": 1,
    }


def _upsert_skill(skills: List[Any], name: str) -> int:
    existing_idx = _find_entry_by_name(skills, name)
    if existing_idx is not None:
        skills[existing_idx] = _make_final_strike_skill(existing_idx)
        return existing_idx

    empty_idx = _find_first_empty_name_slot(skills)
    if empty_idx is not None:
        skills[empty_idx] = _make_final_strike_skill(empty_idx)
        return empty_idx

    new_id = len(skills)
    skills.append(_make_final_strike_skill(new_id))
    return new_id


def _get_actor(actors: List[Any], actor_id: int) -> Dict[str, Any]:
    if actor_id <= 0 or actor_id >= len(actors) or not isinstance(actors[actor_id], dict):
        raise ValueError(f"Actor not found: id={actor_id}")
    return actors[actor_id]


def _get_class(classes: List[Any], class_id: int) -> Dict[str, Any]:
    if class_id <= 0 or class_id >= len(classes) or not isinstance(classes[class_id], dict):
        raise ValueError(f"Class not found: id={class_id}")
    return classes[class_id]


def _ensure_system_skill_type(system: Dict[str, Any], stype_id: int, label: str) -> None:
    skill_types = system.get("skillTypes")
    if not isinstance(skill_types, list):
        raise ValueError("System.skillTypes is missing or invalid")

    while len(skill_types) <= stype_id:
        skill_types.append("")
    if (skill_types[stype_id] or "") == "":
        skill_types[stype_id] = label


def _ensure_class_has_skill_type(cl: Dict[str, Any], stype_id: int) -> None:
    traits = cl.get("traits")
    if not isinstance(traits, list):
        raise ValueError("Class.traits is missing or invalid")
    for t in traits:
        if isinstance(t, dict) and t.get("code") == 41 and t.get("dataId") == stype_id:
            return
    traits.append({"code": 41, "dataId": stype_id, "value": 1})


def _ensure_class_learns_skill_at_level_one(cl: Dict[str, Any], skill_id: int) -> None:
    learnings = cl.get("learnings")
    if not isinstance(learnings, list):
        raise ValueError("Class.learnings is missing or invalid")
    for l in learnings:
        if isinstance(l, dict) and l.get("skillId") == skill_id:
            if l.get("level") != 1:
                l["level"] = 1
            if "note" not in l:
                l["note"] = ""
            return
    learnings.append({"level": 1, "note": "", "skillId": skill_id})


def main(argv: List[str]) -> int:
    if argv:
        print("Usage: python edit_skills.py", file=sys.stderr)
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

    skill_id = _upsert_skill(skills, "최후의 일격")
    _ensure_system_skill_type(system, 5, "필살기")
    _ensure_class_has_skill_type(cl, 5)
    _ensure_class_learns_skill_at_level_one(cl, skill_id)

    _dump_rmmz_array_json(_skills_path(), skills, skills_nl)
    _dump_rmmz_object_json(_system_path(), system, system_nl)
    _dump_rmmz_array_json(_classes_path(), classes, classes_nl)

    actor_name = str(lead.get("name") or "Actor1")
    class_name = str(cl.get("name") or f"Class{class_id}")
    print(
        f'OK: Added/updated skill "최후의 일격" (id={skill_id}, stypeId=5) and assigned to actor1 ({actor_name}) via class {class_id} ({class_name}).'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

