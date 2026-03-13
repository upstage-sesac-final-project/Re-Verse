import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import copy
import json


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _enemies_path() -> Path:
    return _project_root() / "data" / "Enemies.json"


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


def _find_enemy_by_name(enemies: List[Any], name: str) -> Optional[int]:
    for idx in range(1, len(enemies)):
        e = enemies[idx]
        if isinstance(e, dict) and (e.get("name") or "") == name:
            return idx
    return None


def _find_first_empty_slot(enemies: List[Any]) -> Optional[int]:
    for idx in range(1, len(enemies)):
        e = enemies[idx]
        if isinstance(e, dict) and (e.get("name") or "") == "":
            return idx
    return None


def _find_dwarf_template(enemies: List[Any]) -> Optional[Dict[str, Any]]:
    idx = _find_enemy_by_name(enemies, "난쟁이")
    if idx is not None and isinstance(enemies[idx], dict):
        return enemies[idx]

    for i in range(1, len(enemies)):
        e = enemies[i]
        if isinstance(e, dict) and (e.get("battlerName") or "") == "Gnome":
            return e
    return None


def _make_crow_enemy(enemy_id: int, dwarf: Dict[str, Any]) -> Dict[str, Any]:
    enemy = copy.deepcopy(dwarf)
    enemy["id"] = enemy_id
    enemy["battlerName"] = "Crow"
    enemy["battlerHue"] = 0
    enemy["name"] = "Crow"
    return enemy


def _make_demon_enemy(enemy_id: int, dwarf: Dict[str, Any]) -> Dict[str, Any]:
    enemy = copy.deepcopy(dwarf)
    enemy["id"] = enemy_id
    enemy["battlerName"] = "Demon"
    enemy["battlerHue"] = 0
    enemy["name"] = "Demon"
    return enemy


def main(argv: List[str]) -> int:
    if len(argv) != 1:
        print("Usage: python edit_enemies.py (crow|demon)", file=sys.stderr)
        return 2

    cmd = argv[0].strip().lower()
    if cmd not in {"crow", "demon"}:
        print(f"Unknown enemy: {argv[0]} (expected crow or demon)", file=sys.stderr)
        return 2

    path = _enemies_path()
    if not path.exists():
        print(f"Missing file: {path}", file=sys.stderr)
        return 2

    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    enemies = json.loads(raw)

    if not isinstance(enemies, list) or not enemies or enemies[0] is not None:
        print("Unexpected Enemies.json format (expected [null, ...])", file=sys.stderr)
        return 2

    dwarf = _find_dwarf_template(enemies)
    if dwarf is None:
        print("Cannot find dwarf template (name=난쟁이 or battlerName=Gnome).", file=sys.stderr)
        return 2

    target_name = "Crow" if cmd == "crow" else "Demon"
    maker = _make_crow_enemy if cmd == "crow" else _make_demon_enemy

    existing_idx = _find_enemy_by_name(enemies, target_name)
    if existing_idx is not None:
        enemies[existing_idx] = maker(existing_idx, dwarf)
        enemy_id = existing_idx
    else:
        empty_idx = _find_first_empty_slot(enemies)
        if empty_idx is not None:
            enemies[empty_idx] = maker(empty_idx, dwarf)
            enemy_id = empty_idx
        else:
            enemy_id = len(enemies)
            enemies.append(maker(enemy_id, dwarf))

    _dump_rmmz_array_json(path, enemies, newline)
    print(f"OK: Enemies.json updated ({target_name} id={enemy_id}, based on 난쟁이)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
