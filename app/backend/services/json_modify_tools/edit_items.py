import json
import sys
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    # return Path(__file__).resolve().parent
    # edit_enemies.py 위치: Re-Verse/app/backend/services/json_modify_tools/
    # parents[4] → Re-Verse/ (프로젝트 루트)
    return Path(__file__).resolve().parents[4]


def _items_path() -> Path:
    return _project_root() / "storage" / "games" / "game_001" / "data" / "Items.json"


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_rmmz_array_json(path: Path, data: list[Any], newline: str) -> None:
    lines: list[str] = ["["]
    for i, entry in enumerate(data):
        s = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        if i != len(data) - 1:
            s += ","
        lines.append(s)
    lines.append("]")
    path.write_text(newline.join(lines) + newline, encoding="utf-8")


def _make_poison_item(item_id: int) -> dict[str, Any]:
    return {
        "id": item_id,
        "animationId": 41,
        "consumable": True,
        "damage": {
            "critical": False,
            "elementId": 0,
            "formula": "b.hp - 1",
            "type": 1,
            "variance": 0,
        },
        "description": "아군 전원의 HP를 1로 만듭니다.",
        "effects": [],
        "hitType": 0,
        "iconIndex": 176,
        "itypeId": 1,
        "name": "독약",
        "note": "",
        "occasion": 0,
        "price": 0,
        "repeats": 1,
        "scope": 8,
        "speed": 0,
        "successRate": 100,
        "tpGain": 0,
    }


def _is_empty_item_slot(item: dict[str, Any]) -> bool:
    return (item.get("name") or "") == ""


def _find_item_by_name(items: list[Any], name: str) -> int | None:
    for idx in range(1, len(items)):
        it = items[idx]
        if isinstance(it, dict) and (it.get("name") or "") == name:
            return idx
    return None


def _find_first_empty_slot(items: list[Any]) -> int | None:
    for idx in range(1, len(items)):
        it = items[idx]
        if isinstance(it, dict) and _is_empty_item_slot(it):
            return idx
    return None


def _upsert_poison_item(items: list[Any]) -> int:
    existing_idx = _find_item_by_name(items, "독약")
    if existing_idx is not None:
        items[existing_idx] = _make_poison_item(existing_idx)
        return existing_idx

    empty_idx = _find_first_empty_slot(items)
    if empty_idx is not None:
        items[empty_idx] = _make_poison_item(empty_idx)
        return empty_idx

    new_id = len(items)
    items.append(_make_poison_item(new_id))
    return new_id


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python edit_itmes.py 독약", file=sys.stderr)
        return 2

    cmd = argv[0].strip()
    if cmd != "독약":
        print(f"Unknown item: {cmd}", file=sys.stderr)
        return 2

    path = _items_path()
    if not path.exists():
        print(f"Missing file: {path}", file=sys.stderr)
        return 2

    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    items = json.loads(raw)

    if not isinstance(items, list) or not items or items[0] is not None:
        print("Unexpected Items.json format (expected [null, ...])", file=sys.stderr)
        return 2

    item_id = _upsert_poison_item(items)
    _dump_rmmz_array_json(path, items, newline)
    print(f"OK: Items.json updated (독약 id={item_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
