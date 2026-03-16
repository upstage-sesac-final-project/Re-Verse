import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import json


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _actors_path() -> Path:
    return _project_root() / "data" / "Actors.json"


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


def _load_array_json(path: Path) -> Tuple[List[Any], str]:
    raw = path.read_text(encoding="utf-8")
    newline = _detect_newline(raw)
    data = json.loads(raw)
    if not isinstance(data, list) or not data or data[0] is not None:
        raise ValueError(f"Unexpected format: {path.name} (expected [null, ...])")
    return data, newline


def _load_object_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: List[str]) -> int:
    if argv:
        print("Usage: python edit_levels.py", file=sys.stderr)
        return 2

    if not _actors_path().exists():
        print(f"Missing file: {_actors_path()}", file=sys.stderr)
        return 2
    if not _system_path().exists():
        print(f"Missing file: {_system_path()}", file=sys.stderr)
        return 2

    system = _load_object_json(_system_path())
    party_members = system.get("partyMembers")
    if not isinstance(party_members, list) or not all(isinstance(x, int) for x in party_members):
        print("System.partyMembers is missing or invalid.", file=sys.stderr)
        return 2

    actors, actors_nl = _load_array_json(_actors_path())

    updated: List[int] = []
    for actor_id in party_members:
        if actor_id <= 0 or actor_id >= len(actors) or not isinstance(actors[actor_id], dict):
            print(f"Actor not found: id={actor_id} (from System.partyMembers)", file=sys.stderr)
            return 2
        actor = actors[actor_id]
        actor["initialLevel"] = 25
        updated.append(actor_id)

    _dump_rmmz_array_json(_actors_path(), actors, actors_nl)
    print(f"OK: Set initialLevel=25 for party members: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

