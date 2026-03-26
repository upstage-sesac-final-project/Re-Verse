"""이벤트/NPC CRUD 연산."""

from typing import Any

from app.backend.services.map_editor.loader import find_free_event_id, validate_bounds

# 기본 이벤트 페이지 조건 블록 (RPG Maker MZ 표준)
_DEFAULT_CONDITIONS: dict[str, Any] = {
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
}

_DEFAULT_MOVE_ROUTE: dict[str, Any] = {
    "list": [{"code": 0, "parameters": []}],
    "repeat": True,
    "skippable": False,
    "wait": False,
}


def _make_event(event_id: int, params: dict[str, Any]) -> dict[str, Any]:
    """RPG Maker MZ 이벤트 객체를 생성한다.

    params 키:
        name (str): 이벤트 이름 (기본: "NPC")
        x (int): X 좌표
        y (int): Y 좌표
        character_name (str): 캐릭터 파일명 (기본: "People1")
        character_index (int): 캐릭터 인덱스 0~7 (기본: 0)
        direction (int): 방향 2=아래 4=왼쪽 6=오른쪽 8=위 (기본: 2)
        dialogue_lines (list[str]): 대사 목록 (기본: [])
        trigger (int): 트리거 0=접근 1=결정키 2=자동 3=대기 (기본: 0)
        move_type (int): 이동 타입 0=고정 1=랜덤 2=접근 3=커스텀 (기본: 0)
    """
    name = params.get("name", "NPC")
    x = params["x"]
    y = params["y"]
    char_name = params.get("character_name", "People1")
    char_index = params.get("character_index", 0)
    direction = params.get("direction", 2)
    dialogue_lines: list[str] = params.get("dialogue_lines", [])
    trigger = params.get("trigger", 0)
    move_type = params.get("move_type", 0)

    # 이벤트 커맨드 리스트 구성
    cmd_list: list[dict[str, Any]] = []
    if dialogue_lines:
        cmd_list.append({"code": 101, "indent": 0, "parameters": [char_name, char_index, 0, 2, ""]})
        for line in dialogue_lines:
            cmd_list.append({"code": 401, "indent": 0, "parameters": [line]})
    cmd_list.append({"code": 0, "indent": 0, "parameters": []})

    return {
        "id": event_id,
        "name": name,
        "note": "",
        "pages": [
            {
                "conditions": dict(_DEFAULT_CONDITIONS),
                "directionFix": False,
                "image": {
                    "tileId": 0,
                    "characterName": char_name,
                    "characterIndex": char_index,
                    "direction": direction,
                    "pattern": 0,
                },
                "list": cmd_list,
                "moveFrequency": 3,
                "moveRoute": dict(_DEFAULT_MOVE_ROUTE),
                "moveSpeed": 3,
                "moveType": move_type,
                "priorityType": 1,
                "stepAnime": False,
                "through": False,
                "trigger": trigger,
                "walkAnime": True,
            }
        ],
        "x": x,
        "y": y,
    }


def add_event(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """맵에 새 이벤트를 추가한다.

    params: name, x, y, character_name, character_index, direction,
            dialogue_lines, trigger, move_type, force (bool — 좌표 충돌 시 덮어쓰기)
    반환: 수정된 map_data
    """
    x, y = params["x"], params["y"]
    force = params.get("force", False)

    if not validate_bounds(map_data, x, y):
        raise ValueError(
            f"좌표 ({x}, {y})가 맵 범위를 벗어났습니다. (width={map_data['width']}, height={map_data['height']})"
        )

    events: list[Any] = map_data.setdefault("events", [None])

    # 좌표 충돌 검사
    if not force:
        for ev in events:
            if ev and ev.get("x") == x and ev.get("y") == y:
                raise ValueError(
                    f"좌표 ({x}, {y})에 이미 이벤트 '{ev['name']}'가 있습니다. force=True로 덮어쓸 수 있습니다."
                )

    event_id = find_free_event_id(events)
    new_event = _make_event(event_id, params)

    if event_id < len(events):
        events[event_id] = new_event
    else:
        events.append(new_event)

    return map_data


def update_event_dialogue(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """기존 이벤트의 대사를 교체한다.

    params: event_id (int) 또는 event_name (str), new_lines (list[str])
    """
    new_lines: list[str] = params["new_lines"]
    event = _find_event(map_data, params)

    for page in event["pages"]:
        cmd_list: list[dict[str, Any]] = page["list"]
        # code=401 항목 모두 제거 후 새 대사로 교체
        non_dialogue = [cmd for cmd in cmd_list if cmd["code"] != 401]
        new_dialogue = [{"code": 401, "indent": 0, "parameters": [line]} for line in new_lines]

        # code=101 헤더 뒤에 새 대사 삽입
        header_idx = next((i for i, cmd in enumerate(non_dialogue) if cmd["code"] == 101), None)
        if header_idx is not None:
            page["list"] = (
                non_dialogue[: header_idx + 1] + new_dialogue + non_dialogue[header_idx + 1 :]
            )
        else:
            # 헤더 없으면 종료자 앞에 삽입
            end_idx = next(
                (i for i, cmd in enumerate(non_dialogue) if cmd["code"] == 0), len(non_dialogue)
            )
            page["list"] = non_dialogue[:end_idx] + new_dialogue + non_dialogue[end_idx:]

    return map_data


def delete_event(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """이벤트를 슬롯에서 None으로 교체한다 (RPG Maker MZ 관례).

    params: event_id (int) 또는 event_name (str)
    """
    event = _find_event(map_data, params)
    event_id = event["id"]
    map_data["events"][event_id] = None
    return map_data


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────


def _find_event(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    events: list[Any] = map_data.get("events", [])

    if "event_id" in params:
        eid = int(params["event_id"])
        if eid < len(events) and events[eid] is not None:
            return events[eid]
        raise ValueError(f"event_id={eid}인 이벤트를 찾을 수 없습니다.")

    if "event_name" in params:
        name = params["event_name"]
        for ev in events:
            if ev and ev.get("name") == name:
                return ev
        raise ValueError(f"이름이 '{name}'인 이벤트를 찾을 수 없습니다.")

    raise ValueError("event_id 또는 event_name 중 하나를 제공해야 합니다.")
