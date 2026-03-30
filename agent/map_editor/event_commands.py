"""RPG Maker MZ 이벤트 커맨드 빌더.

지원 커맨드:
    dialogue      → 101 (메시지 창) + 401 (대사 줄)
    choice        → 102 (선택지)
    condition     → 111 (조건 분기) + 412 (분기 끝)
    switch        → 121 (스위치 조작)
    variable      → 122 (변수 조작)
    self_switch   → 123 (셀프 스위치 조작)
    transfer      → 201 (장소 이동)
    wait          → 230 (웨이트)
"""

from typing import Any


def _cmd(code: int, indent: int, params: list[Any]) -> dict[str, Any]:
    return {"code": code, "indent": indent, "parameters": params}


def build_dialogue(
    lines: list[str],
    char_name: str = "",
    char_index: int = 0,
    face_name: str = "",
    face_index: int = 0,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """대사 커맨드 블록을 생성한다.

    101: [face_name, face_index, background, position, speaker_name]
    401: [line]
    """
    cmds: list[dict[str, Any]] = []
    cmds.append(_cmd(101, indent, [face_name, face_index, 0, 2, char_name]))
    for line in lines:
        cmds.append(_cmd(401, indent, [line]))
    return cmds


def build_choice(
    choices: list[str],
    cancel_type: int = 2,
    default_type: int = 0,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """선택지 커맨드를 생성한다.

    102: [choices, cancel_type, default_type, position, background]
    """
    return [_cmd(102, indent, [choices, cancel_type, default_type, 0, 0])]


def build_condition_branch(
    switch_id: int | None = None,
    variable_id: int | None = None,
    variable_value: int = 0,
    self_switch: str | None = None,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """조건 분기(111) + 분기 끝(412) 커맨드 쌍을 생성한다.

    type: 0=스위치 1=변수 2=셀프스위치 ...
    """
    if switch_id is not None:
        params = [0, switch_id, 0]  # type 0, switch_id, on(0)/off(1)
    elif variable_id is not None:
        params = [1, variable_id, 0, variable_value, 0]  # type 1, var_id, op(≥0), value, ...
    elif self_switch is not None:
        params = [2, self_switch, 0]  # type 2, key, on(0)/off(1)
    else:
        params = [0, 1, 0]

    return [
        _cmd(111, indent, params),
        _cmd(412, indent, []),
    ]


def build_switch(
    switch_id: int,
    switch_id2: int | None = None,
    value: int = 0,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """스위치 조작(121) 커맨드를 생성한다.

    121: [start_id, end_id, value(0=ON 1=OFF 2=Toggle)]
    """
    end_id = switch_id2 if switch_id2 is not None else switch_id
    return [_cmd(121, indent, [switch_id, end_id, value])]


def build_variable(
    variable_id: int,
    operation: int = 0,
    operand_type: int = 0,
    value: int = 0,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """변수 조작(122) 커맨드를 생성한다.

    122: [start_id, end_id, operation(0=Set), operand_type(0=const), value]
    operation: 0=Set 1=Add 2=Sub 3=Mul 4=Div 5=Mod
    """
    return [_cmd(122, indent, [variable_id, variable_id, operation, operand_type, value])]


def build_self_switch(
    key: str = "A",
    value: int = 0,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """셀프 스위치 조작(123) 커맨드를 생성한다.

    123: [key, value(0=ON 1=OFF)]
    """
    return [_cmd(123, indent, [key, value])]


def build_transfer(
    map_id: int,
    x: int,
    y: int,
    direction: int = 0,
    fade_type: int = 0,
    indent: int = 0,
) -> list[dict[str, Any]]:
    """장소 이동(201) 커맨드를 생성한다.

    201: [mode(0=direct), map_id, x, y, direction, fade_type]
    """
    return [_cmd(201, indent, [0, map_id, x, y, direction, fade_type])]


def build_wait(frames: int = 60, indent: int = 0) -> list[dict[str, Any]]:
    """웨이트(230) 커맨드를 생성한다."""
    return [_cmd(230, indent, [frames])]


def build_end(indent: int = 0) -> list[dict[str, Any]]:
    """이벤트 종료(0) 커맨드를 생성한다."""
    return [_cmd(0, indent, [])]


# ── 고수준 빌더: spec dict → 커맨드 리스트 ────────────────────────────────────


def build_commands(command_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """command_specs 목록을 RPG Maker MZ 커맨드 리스트로 변환한다.

    각 spec 형식:
        {"type": "dialogue", "lines": [...], "char_name": "...", ...}
        {"type": "choice", "choices": [...]}
        {"type": "condition", "switch_id": 1}
        {"type": "switch", "switch_id": 1, "value": 0}
        {"type": "variable", "variable_id": 1, "value": 10}
        {"type": "self_switch", "key": "A", "value": 0}
        {"type": "transfer", "map_id": 1, "x": 5, "y": 5}
        {"type": "wait", "frames": 60}
    """
    result: list[dict[str, Any]] = []
    indent = 0

    for spec in command_specs:
        t = spec.get("type", "")
        if t == "dialogue":
            result.extend(
                build_dialogue(
                    lines=spec.get("lines", []),
                    char_name=spec.get("char_name", ""),
                    char_index=spec.get("char_index", 0),
                    face_name=spec.get("face_name", ""),
                    face_index=spec.get("face_index", 0),
                    indent=indent,
                )
            )
        elif t == "choice":
            result.extend(build_choice(choices=spec.get("choices", []), indent=indent))
        elif t == "condition":
            result.extend(
                build_condition_branch(
                    switch_id=spec.get("switch_id"),
                    variable_id=spec.get("variable_id"),
                    variable_value=spec.get("variable_value", 0),
                    self_switch=spec.get("self_switch"),
                    indent=indent,
                )
            )
        elif t == "switch":
            result.extend(
                build_switch(
                    switch_id=spec["switch_id"],
                    switch_id2=spec.get("switch_id2"),
                    value=spec.get("value", 0),
                    indent=indent,
                )
            )
        elif t == "variable":
            result.extend(
                build_variable(
                    variable_id=spec["variable_id"],
                    operation=spec.get("operation", 0),
                    operand_type=spec.get("operand_type", 0),
                    value=spec.get("value", 0),
                    indent=indent,
                )
            )
        elif t == "self_switch":
            result.extend(
                build_self_switch(
                    key=spec.get("key", "A"), value=spec.get("value", 0), indent=indent
                )
            )
        elif t == "transfer":
            result.extend(
                build_transfer(
                    map_id=spec["map_id"],
                    x=spec["x"],
                    y=spec["y"],
                    direction=spec.get("direction", 0),
                    fade_type=spec.get("fade_type", 0),
                    indent=indent,
                )
            )
        elif t == "wait":
            result.extend(build_wait(frames=spec.get("frames", 60), indent=indent))

    result.extend(build_end(indent=0))
    return result
