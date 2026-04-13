"""샘플맵 exits 역추적 스크립트 (1회 전처리).

각 MapXXX.json의 events에서 Transfer Player 명령(code 201)을 찾아
`leads_to_id` / `leads_to_name`을 채운다.

실행:
    uv run python -m agent.generation.mapgen.resolve_exits
"""

import json
import re
from pathlib import Path
from typing import Any

_MAPGEN_DIR = Path(__file__).parent
_METADATA_PATH = _MAPGEN_DIR / "data" / "map_metadata.json"
_SAMPLEMAPS_DIR = _MAPGEN_DIR.parents[1] / "rag" / "data" / "samplemaps"

_FILE_ID_RE = re.compile(r"Map(\d+)\.json")

# RPG Maker MZ Transfer Player 명령 코드
CODE_TRANSFER = 201


def _parse_map_id(file_name: str) -> int | None:
    m = _FILE_ID_RE.match(file_name)
    return int(m.group(1)) if m else None


def _direction_label(ev_x: int, ev_y: int, width: int, height: int) -> str:
    """이벤트 좌표로부터 대략적인 방향 라벨을 계산."""
    fx = ev_x / max(1, width - 1)
    fy = ev_y / max(1, height - 1)
    # 경계에 가까운 쪽 우선
    if fy <= 0.2:
        return "north"
    if fy >= 0.8:
        return "south"
    if fx <= 0.2:
        return "west"
    if fx >= 0.8:
        return "east"
    return "center"


def _collect_transfers(map_json: dict[str, Any]) -> list[dict[str, Any]]:
    """단일 맵의 events에서 Transfer 명령을 긁어모은다."""
    out: list[dict[str, Any]] = []
    width = map_json.get("width", 0)
    height = map_json.get("height", 0)
    events = map_json.get("events") or []
    for ev in events:
        if not ev:
            continue
        ev_x = ev.get("x", 0)
        ev_y = ev.get("y", 0)
        for page in ev.get("pages", []) or []:
            for cmd in page.get("list", []) or []:
                if cmd.get("code") != CODE_TRANSFER:
                    continue
                params = cmd.get("parameters") or []
                # parameters: [designation, mapId, x, y, direction, fadeType]
                # designation 0 = 직접 지정, 1 = 변수 지정 (후자는 스킵)
                if len(params) < 4 or params[0] != 0:
                    continue
                target_id = int(params[1])
                if target_id <= 0:
                    continue
                out.append(
                    {
                        "coord": [ev_x, ev_y],
                        "direction": _direction_label(ev_x, ev_y, width, height),
                        "leads_to_id": target_id,
                        "leads_to_name": "Unknown",  # 나중에 메타데이터로 채움
                    }
                )
    return out


def main() -> None:
    metadata = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))

    # map_id → display_name 조회 테이블
    id_to_name: dict[int, str] = {}
    for entry in metadata:
        mid = _parse_map_id(entry["file_name"])
        if mid is not None:
            id_to_name[mid] = entry.get("display_name") or entry["file_name"]

    resolved_maps = 0
    total_exits = 0
    named_exits = 0

    for entry in metadata:
        file_path = _SAMPLEMAPS_DIR / entry["file_name"]
        if not file_path.exists():
            continue
        try:
            map_json = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  {entry['file_name']} 파싱 실패: {e}")
            continue

        exits = _collect_transfers(map_json)
        # leads_to_name 채우기
        for ex in exits:
            name = id_to_name.get(ex["leads_to_id"])
            if name:
                ex["leads_to_name"] = name
                named_exits += 1

        entry["exits"] = exits
        total_exits += len(exits)
        if exits:
            resolved_maps += 1

    _METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"처리 완료: {len(metadata)}개 맵")
    print(f"exits 보유: {resolved_maps}개 맵")
    print(f"총 exits: {total_exits}개, 이름 해결: {named_exits}개")
    print(f"출력: {_METADATA_PATH}")


if __name__ == "__main__":
    main()
