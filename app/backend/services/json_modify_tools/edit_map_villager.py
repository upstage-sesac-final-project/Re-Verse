import argparse
import json
import sys
from pathlib import Path
from typing import Any

NPC_X = 20
NPC_Y = 9
NPC_EVENT_NAME = "Villager"

NPC_CHARACTER_NAME = "People2"
NPC_CHARACTER_INDEX = 4
NPC_DIRECTION = 4
NPC_PATTERN = 1

TEXT_LINES = [
    "마왕성에 가려면 조건이 필요합니다.",
    "그중 요정의 축복을 받은 무기는 비밀의 숲에 있어요.",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_map_path(map_arg: str) -> Path:
    s = map_arg.strip().strip('"')
    if s.isdigit():
        return _project_root() / "storage" / "games" / "game_001" / "data" / f"Map{int(s):03d}.json"
    p = Path(s)
    if p.is_absolute():
        return p
    return _project_root() / p


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, obj: dict[str, Any]) -> None:
    # Keep files compact (Map data arrays are huge); RPG Maker MZ reads compact JSON fine.
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _make_villager_event(event_id: int) -> dict[str, Any]:
    return {
        "id": event_id,
        "name": NPC_EVENT_NAME,
        "note": "",
        "pages": [
            {
                "conditions": {
                    "actorId": 1,
                    "actorValid": False,
                    "itemId": 1,
                    "itemValid": False,
                    "selfSwitchCh": "A",
                    "selfSwitchValid": False,
                    "switch1Id": 1,
                    "switch1Valid": False,
                    "switch2Id": 1,
                    "switch2Valid": False,
                    "variableId": 1,
                    "variableValid": False,
                    "variableValue": 0,
                },
                "directionFix": False,
                "image": {
                    "tileId": 0,
                    "characterName": NPC_CHARACTER_NAME,
                    "direction": NPC_DIRECTION,
                    "pattern": NPC_PATTERN,
                    "characterIndex": NPC_CHARACTER_INDEX,
                },
                "list": [
                    {
                        "code": 101,
                        "indent": 0,
                        "parameters": [NPC_CHARACTER_NAME, NPC_CHARACTER_INDEX, 0, 2, ""],
                    },
                    *[
                        {"code": 401, "indent": 0, "parameters": [line]}
                        for line in TEXT_LINES
                        if line.strip()
                    ],
                    {"code": 0, "indent": 0, "parameters": []},
                ],
                "moveFrequency": 3,
                "moveRoute": {
                    "list": [{"code": 0, "parameters": []}],
                    "repeat": True,
                    "skippable": False,
                    "wait": False,
                },
                "moveSpeed": 3,
                "moveType": 0,
                "priorityType": 1,
                "stepAnime": False,
                "through": False,
                "trigger": 0,
                "walkAnime": True,
            }
        ],
        "x": NPC_X,
        "y": NPC_Y,
    }


def _find_existing_event_at(events: list[Any], x: int, y: int) -> dict[str, Any] | None:
    for ev in events[1:]:
        if not isinstance(ev, dict):
            continue
        if ev.get("x") == x and ev.get("y") == y:
            return ev
    return None


def _find_free_event_id(events: list[Any]) -> int:
    for idx in range(1, len(events)):
        if events[idx] is None:
            return idx
    return len(events)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"Add a villager NPC event at fixed position (x={NPC_X},y={NPC_Y}) with graphic "
            f'characterName="{NPC_CHARACTER_NAME}".'
        )
    )
    parser.add_argument("map", help='Map path (e.g. "data/Map002.json") or map id (e.g. 2).')
    parser.add_argument(
        "--force",
        action="store_true",
        help=f"If an event already exists at (x={NPC_X},y={NPC_Y}), overwrite it instead of aborting.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not write; only report what would change."
    )
    args = parser.parse_args(argv)

    map_path = _resolve_map_path(args.map)
    if not map_path.exists():
        print(f"ERROR: Map file not found: {map_path}", file=sys.stderr)
        return 1

    data = _load_json(map_path)
    if not isinstance(data, dict):
        print(f"ERROR: Invalid map JSON (expected object): {map_path}", file=sys.stderr)
        return 1

    width = data.get("width")
    height = data.get("height")
    if isinstance(width, int) and isinstance(height, int):
        if NPC_X < 0 or NPC_Y < 0 or NPC_X >= width or NPC_Y >= height:
            print(
                f"ERROR: NPC position (x={NPC_X},y={NPC_Y}) is outside map bounds (width={width},height={height}).",
                file=sys.stderr,
            )
            return 1

    events = data.get("events")
    if not isinstance(events, list) or not events:
        print('ERROR: Invalid map JSON: missing "events" array.', file=sys.stderr)
        return 1
    if events[0] is not None:
        print("ERROR: Unexpected map JSON: events[0] is not null.", file=sys.stderr)
        return 1

    existing = _find_existing_event_at(events, NPC_X, NPC_Y)
    if existing is not None and not args.force:
        print(
            f"ERROR: Event already exists at (x={NPC_X},y={NPC_Y}) with id={existing.get('id')}. "
            "Re-run with --force to overwrite.",
            file=sys.stderr,
        )
        return 2

    if existing is not None:
        event_id = int(existing.get("id") or 0)
        if event_id <= 0 or event_id >= len(events) or events[event_id] is not existing:
            event_id = _find_free_event_id(events)
        new_event = _make_villager_event(event_id)
        if args.dry_run:
            print(f"DRY RUN: Would overwrite event id={event_id} in {map_path}")
            return 0
        events[event_id] = new_event
        data["events"] = events
        _dump_json(map_path, data)
        print(f"OK: Overwrote event id={event_id} at (x={NPC_X},y={NPC_Y}) in {map_path}")
        return 0

    event_id = _find_free_event_id(events)
    new_event = _make_villager_event(event_id)

    if args.dry_run:
        print(f"DRY RUN: Would add event id={event_id} at (x={NPC_X},y={NPC_Y}) in {map_path}")
        return 0

    if event_id == len(events):
        events.append(new_event)
    else:
        events[event_id] = new_event

    data["events"] = events
    _dump_json(map_path, data)
    print(f"OK: Added event id={event_id} at (x={NPC_X},y={NPC_Y}) in {map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
