"""맵 데이터 유효성 검사."""

from typing import Any


def validate_map(map_data: dict[str, Any]) -> list[str]:
    """맵 데이터의 무결성을 검사하고 오류 목록을 반환한다.

    검사 항목:
    1. data 배열 길이 = 6 * width * height
    2. 이벤트 ID 일관성 (events[i].id == i)
    3. 이벤트 좌표 범위 (0 <= x < width, 0 <= y < height)
    4. 커맨드 블록 매칭 (101 헤더가 있으면 401 or 0이 뒤따름)
    5. 이벤트 배열 중복 ID 없음
    """
    errors: list[str] = []

    w = map_data.get("width", 0)
    h = map_data.get("height", 0)
    data = map_data.get("data", [])
    expected_len = 6 * w * h

    # 1. data 길이
    if len(data) != expected_len:
        errors.append(f"data 배열 길이 불일치: {len(data)} (예상 {expected_len} = 6×{w}×{h})")

    events: list[Any] = map_data.get("events", [])
    seen_ids: set[int] = set()

    for i, ev in enumerate(events):
        if ev is None:
            continue

        ev_id = ev.get("id")

        # 2. ID 일관성
        if ev_id != i:
            errors.append(f"events[{i}].id={ev_id} 불일치 (인덱스 {i}여야 함)")

        # 5. 중복 ID
        if ev_id in seen_ids:
            errors.append(f"이벤트 ID 중복: {ev_id}")
        else:
            seen_ids.add(ev_id)

        # 3. 좌표 범위
        x, y = ev.get("x", -1), ev.get("y", -1)
        if not (0 <= x < w):
            errors.append(f"이벤트 '{ev.get('name')}' (id={ev_id}) x={x} 범위 초과 (0~{w - 1})")
        if not (0 <= y < h):
            errors.append(f"이벤트 '{ev.get('name')}' (id={ev_id}) y={y} 범위 초과 (0~{h - 1})")

        # 4. 커맨드 블록 검사
        for page in ev.get("pages", []):
            cmd_list = page.get("list", [])
            for j, cmd in enumerate(cmd_list):
                if cmd["code"] == 101:
                    # 다음 커맨드가 401 또는 0 이어야 함
                    if j + 1 < len(cmd_list) and cmd_list[j + 1]["code"] not in (401, 0):
                        errors.append(
                            f"이벤트 id={ev_id}: 101 커맨드 다음에 401/0이 아닌 코드 {cmd_list[j + 1]['code']}"
                        )

    return errors
