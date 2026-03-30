"""이벤트/NPC CRUD 연산."""

from typing import Any

from agent.map_editor.event_commands import build_commands, build_dialogue, build_end
from agent.map_editor.loader import find_free_event_id

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
        x (int), y (int): 좌표
        character_name (str): 캐릭터 파일명 (기본: "People1")
        character_index (int 0~7): 캐릭터 인덱스 (기본: 0)
        direction (int 2/4/6/8): 방향 (기본: 2 = 아래)
        dialogue_lines (list[str]): 단순 대사 목록 (기본: [])
        commands (list[dict]): 고수준 커맨드 spec 목록 — dialogue_lines보다 우선
        trigger (int 0~3): 트리거 (기본: 0 = 접근)
        move_type (int 0~3): 이동 타입 (기본: 0 = 고정)
    """
    name = params.get("name", "NPC")
    x = params["x"]
    y = params["y"]
    char_name = params.get("character_name", "People1")
    char_index = params.get("character_index", 0)
    direction = params.get("direction", 2)
    trigger = params.get("trigger", 0)
    move_type = params.get("move_type", 0)

    # commands spec이 있으면 고수준 빌더 사용, 없으면 dialogue_lines 단순 처리
    command_specs = params.get("commands")
    if command_specs:
        cmd_list = build_commands(command_specs)
    else:
        dialogue_lines: list[str] = params.get("dialogue_lines", [])
        if dialogue_lines:
            cmd_list = (
                build_dialogue(lines=dialogue_lines, char_name=char_name, char_index=char_index)
                + build_end()
            )
        else:
            cmd_list = build_end()

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
    """맵에 새 이벤트를 추가한다."""
    x, y = params["x"], params["y"]
    force = params.get("force", False)

    w, h = map_data["width"], map_data["height"]
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError(f"좌표 ({x},{y})가 맵 범위(width={w}, height={h})를 벗어났습니다.")

    events: list[Any] = map_data.setdefault("events", [None])

    if not force:
        for ev in events:
            if ev and ev.get("x") == x and ev.get("y") == y:
                raise ValueError(
                    f"좌표 ({x},{y})에 이미 이벤트 '{ev['name']}'가 있습니다. force=True로 덮어쓰기 가능합니다."
                )

    event_id = find_free_event_id(events)
    new_event = _make_event(event_id, params)

    if event_id < len(events):
        events[event_id] = new_event
    else:
        events.append(new_event)

    return map_data


def update_event_dialogue(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """이벤트의 대사(401 코드)를 새 대사로 교체한다.

    params: (event_id 또는 event_name), new_lines (list[str])
    """
    new_lines: list[str] = params["new_lines"]
    event = _find_event(map_data, params)

    for page in event["pages"]:
        cmd_list: list[dict[str, Any]] = page["list"]
        non_dialogue = [cmd for cmd in cmd_list if cmd["code"] != 401]
        new_dialogue = [{"code": 401, "indent": 0, "parameters": [line]} for line in new_lines]

        header_idx = next((i for i, cmd in enumerate(non_dialogue) if cmd["code"] == 101), None)
        if header_idx is not None:
            page["list"] = (
                non_dialogue[: header_idx + 1] + new_dialogue + non_dialogue[header_idx + 1 :]
            )
        else:
            end_idx = next(
                (i for i, cmd in enumerate(non_dialogue) if cmd["code"] == 0), len(non_dialogue)
            )
            page["list"] = non_dialogue[:end_idx] + new_dialogue + non_dialogue[end_idx:]

    return map_data


def update_event_commands(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """이벤트의 커맨드 리스트 전체를 교체한다.

    params: (event_id 또는 event_name), commands (list[dict] command specs)
    """
    event = _find_event(map_data, params)
    command_specs = params["commands"]
    cmd_list = build_commands(command_specs)

    for page in event["pages"]:
        page["list"] = cmd_list

    return map_data


def delete_event(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """이벤트를 None으로 교체한다 (RPG Maker MZ 관례)."""
    event = _find_event(map_data, params)
    map_data["events"][event["id"]] = None
    return map_data


def _find_event(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    events: list[Any] = map_data.get("events", [])

    if "event_id" in params:
        eid = int(params["event_id"])
        if 0 < eid < len(events) and events[eid] is not None:
            return events[eid]
        raise ValueError(f"event_id={eid} 이벤트를 찾을 수 없습니다.")

    if "event_name" in params:
        name = params["event_name"]
        for ev in events:
            if ev and ev.get("name") == name:
                return ev
        raise ValueError(f"이름 '{name}' 이벤트를 찾을 수 없습니다.")

    raise ValueError("event_id 또는 event_name 중 하나가 필요합니다.")
