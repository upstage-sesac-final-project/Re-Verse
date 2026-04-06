# 맵 연결 상세 설계

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 문제 정의

`game_designer` LLM이 생성하는 `GameSpec.maps[i].connects_to`는 단방향이다:

```python
maps = [
    MapSpec(name="마을",  connects_to=["던전"]),       # 마을→던전만 명시
    MapSpec(name="던전",  connects_to=["보스 방"]),    # 던전→마을 누락!
    MapSpec(name="보스 방", connects_to=[]),           # 막힌 방
]
```

이 상태로 진행하면:
- 마을에서 던전으로 가는 Transfer 이벤트는 생성됨
- 던전에서 마을로 돌아오는 Transfer 이벤트가 없음 → 플레이어 갇힘 (R21)

---

## R21. 비대칭 connects_to → 편도 이동만 가능 (P1)

### 완화 전략

연결 그래프를 **자동으로 양방향 정규화**한다.
두 맵 중 어느 하나라도 상대를 `connects_to`에 포함하면 양방향으로 처리한다.

```python
def normalize_connections(maps: list[MapSpec]) -> list[MapSpec]:
    """
    connects_to 그래프를 양방향(undirected)으로 정규화.
    단방향 연결 발견 시 반대쪽에 자동 추가.
    boss 타입 맵은 예외: boss → 이전 맵 방향만 추가 (진입 방향 유지)
    """
    name_to_spec = {m.name: m for m in maps}
    connections: dict[str, set[str]] = {m.name: set(m.connects_to) for m in maps}

    # 단방향 연결 감지 및 역방향 추가
    for src_name, targets in list(connections.items()):
        for tgt_name in targets:
            if tgt_name not in connections:
                continue  # 존재하지 않는 맵 이름 (validator가 처리)
            if src_name not in connections[tgt_name]:
                # boss 맵은 출구를 하나만 허용 (선택적 규칙)
                tgt_spec = name_to_spec.get(tgt_name)
                if tgt_spec and tgt_spec.type == "boss":
                    pass  # 보스 방에서 나가는 연결 추가 안 함 (엔딩 처리)
                else:
                    connections[tgt_name].add(src_name)

    # 정규화된 connects_to 적용
    result = []
    for m in maps:
        normalized = m.model_copy(update={"connects_to": sorted(connections[m.name])})
        result.append(normalized)
    return result
```

### 연결성 BFS 검증

모든 맵이 시작 맵에서 도달 가능한지 BFS로 확인:

```python
def validate_map_connectivity(maps: list[MapSpec]) -> list[str]:
    """
    시작 맵(type='town' 또는 첫 번째 맵)에서 BFS로
    모든 맵이 도달 가능한지 검증.
    """
    if not maps:
        return ["맵이 없음"]

    name_to_map = {m.name: m for m in maps}
    start = next((m for m in maps if m.type == "town"), maps[0])

    visited: set[str] = set()
    queue: deque[str] = deque([start.name])
    visited.add(start.name)

    while queue:
        current_name = queue.popleft()
        current = name_to_map.get(current_name)
        if not current:
            continue
        for neighbor in current.connects_to:
            if neighbor not in visited and neighbor in name_to_map:
                visited.add(neighbor)
                queue.append(neighbor)

    unreachable = [m.name for m in maps if m.name not in visited]
    if unreachable:
        return [f"도달 불가능한 맵: {unreachable}"]
    return []
```

### 적용 위치

1. **game_designer.py** 내 `_parse_game_spec()`:
   ```python
   def _parse_game_spec(raw_spec: GameSpec) -> GameSpec:
       maps = normalize_connections(raw_spec.maps)
       errors = validate_map_connectivity(maps)
       if errors:
           raise ValueError(f"맵 연결성 오류: {errors}")
       return raw_spec.model_copy(update={"maps": maps})
   ```

2. **generation_validator.py** 내 최종 검증 (이중 안전망):
   ```python
   errors += validate_map_connectivity(state["map_specs"])
   ```

---

## 출구 좌표 계산

맵 연결이 정규화되면 각 맵의 출구(exit) 좌표를 계산한다.
출구 좌표는 이벤트 기획자(F)에 주입되어 transfer 이벤트 위치로 사용된다.

### 출구 방향 규칙

두 맵의 관계에 따라 출구 방향을 결정한다:

| 연결 패턴 | 맵 A 출구 | 맵 B 출구 |
|-----------|---------|---------|
| town → dungeon | 남쪽 (하단 중앙) | 북쪽 (상단 중앙) |
| dungeon → boss | 남쪽 (하단 중앙) | 북쪽 (상단 중앙) |
| town ↔ field | 동쪽 (우측 중앙) | 서쪽 (좌측 중앙) |

일반 규칙:
- `town/field → dungeon/boss`: 진행 방향 = 남 또는 동
- `dungeon/boss → town/field`: 귀환 방향 = 북 또는 서

```python
from enum import Enum

class ExitDirection(str, Enum):
    NORTH = "north"   # 맵 상단 중앙
    SOUTH = "south"   # 맵 하단 중앙
    EAST  = "east"    # 맵 우측 중앙
    WEST  = "west"    # 맵 좌측 중앙

def determine_exit_direction(
    src_type: str, tgt_type: str
) -> tuple[ExitDirection, ExitDirection]:
    """
    소스 맵의 출구 방향과 타겟 맵의 입구 방향 반환.
    Returns: (src_exit_direction, tgt_entry_direction)
    """
    progression = {("town", "dungeon"), ("town", "boss"), ("field", "dungeon"),
                   ("dungeon", "boss")}
    regression  = {("dungeon", "town"), ("boss", "dungeon"), ("boss", "town"),
                   ("dungeon", "field")}

    pair = (src_type, tgt_type)
    if pair in progression:
        return ExitDirection.SOUTH, ExitDirection.NORTH
    if pair in regression:
        return ExitDirection.NORTH, ExitDirection.SOUTH
    # town ↔ field 등 같은 레벨
    return ExitDirection.EAST, ExitDirection.WEST

def exit_direction_to_coord(
    direction: ExitDirection, width: int, height: int
) -> tuple[int, int]:
    """맵 크기에서 출구 타일 좌표 계산."""
    match direction:
        case ExitDirection.NORTH: return width  // 2, 0
        case ExitDirection.SOUTH: return width  // 2, height - 1
        case ExitDirection.EAST:  return width  - 1, height // 2
        case ExitDirection.WEST:  return 0,           height // 2
```

### MapConnectionInfo 전체 구성

```python
@dataclass
class ExitInfo:
    target_map_id: int
    exit_x: int        # 이 맵에서 나가는 타일 좌표
    exit_y: int
    entry_x: int       # 타겟 맵에서 도착하는 타일 좌표
    entry_y: int

@dataclass
class MapConnectionInfo:
    map_id: int
    spawn_x: int       # 이 맵에 처음 진입 시 플레이어 위치
    spawn_y: int
    exits: list[ExitInfo]

def calculate_all_connection_info(
    map_specs: list[MapSpec],
    id_table: IdTable,
    map_tiles: dict[int, list[int]],
) -> dict[int, MapConnectionInfo]:
    """
    정규화된 map_specs에서 전체 맵의 연결 정보를 계산한다.
    event_planner에 주입하기 위한 데이터.
    """
    name_to_spec = {m.name: m for m in map_specs}
    result: dict[int, MapConnectionInfo] = {}

    for spec in map_specs:
        src_id = id_table.get_id("maps", spec.name)
        tiles  = map_tiles[src_id]
        w, h   = spec.width, spec.height

        # 스폰 포인트: BFS로 walkable 타일
        spawn = calculate_spawn_point(tiles, w, h) or (w // 2, h // 2)

        exits: list[ExitInfo] = []
        for tgt_name in spec.connects_to:
            tgt_spec = name_to_spec.get(tgt_name)
            if tgt_spec is None:
                continue
            tgt_id = id_table.get_id("maps", tgt_name)
            tgt_tiles = map_tiles[tgt_id]
            tw, th = tgt_spec.width, tgt_spec.height

            # 출구/입구 방향 결정
            src_dir, tgt_dir = determine_exit_direction(spec.type, tgt_spec.type)
            exit_x, exit_y   = exit_direction_to_coord(src_dir, w, h)
            entry_x, entry_y = exit_direction_to_coord(tgt_dir, tw, th)

            # 타일 생성기가 해당 위치를 walkable로 만들었는지 확인
            # 못 만든 경우 BFS로 가장 가까운 walkable 타일 사용
            if not _is_walkable_at(tiles, exit_x, exit_y, w):
                exit_x, exit_y = _nearest_walkable(tiles, exit_x, exit_y, w, h) or (exit_x, exit_y)
            if not _is_walkable_at(tgt_tiles, entry_x, entry_y, tw):
                entry_x, entry_y = _nearest_walkable(tgt_tiles, entry_x, entry_y, tw, th) or (entry_x, entry_y)

            exits.append(ExitInfo(
                target_map_id=tgt_id,
                exit_x=exit_x, exit_y=exit_y,
                entry_x=entry_x, entry_y=entry_y,
            ))

        result[src_id] = MapConnectionInfo(
            map_id=src_id,
            spawn_x=spawn[0], spawn_y=spawn[1],
            exits=exits,
        )

    return result
```

---

## 타일 생성기와의 협력

타일 생성기(E)는 출구 방향을 미리 알아야 해당 위치에 walkable 타일을 배치할 수 있다.

### 해결책: 출구 정보를 타일 생성기에 전달

```python
def generate_map(
    spec: MapSpec,
    connection_info: MapConnectionInfo | None,
    seed: int,
) -> list[int]:
    """
    connection_info가 있으면 출구 좌표를 타일 배열에 강제로 walkable로 설정.
    """
    if spec.type == "town":
        tiles = _generate_town(spec, seed)
    else:
        tiles = _generate_dungeon(spec, seed)

    # 출구 좌표 강제 walkable 처리
    if connection_info:
        for exit_info in connection_info.exits:
            _force_walkable(tiles, exit_info.exit_x, exit_info.exit_y, spec.width)
            # 출구 주변 1칸도 walkable (도착 후 이동 가능 보장)
            for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                nx, ny = exit_info.exit_x + dx, exit_info.exit_y + dy
                if 0 <= nx < spec.width and 0 <= ny < spec.height:
                    _force_walkable(tiles, nx, ny, spec.width)

    return tiles
```

### 수정된 map_designer 워크플로우

```python
async def run_map_designer(state: GenerationState) -> dict:
    spec      = state["game_spec"]
    id_table  = state["id_table"]

    # 1. LLM → MapSpec 목록 (connects_to 포함)
    raw_map_specs: list[MapSpec] = cast(
        MapSpecListOutput,
        await invoke_llm(messages, structured_output=MapSpecListOutput),
    ).maps

    # 2. connects_to 정규화 (양방향)
    map_specs = normalize_connections(raw_map_specs)
    errors = validate_map_connectivity(map_specs)
    if errors:
        raise ValueError(f"맵 연결 오류: {errors}")

    # 3. 임시 connection_info (좌표 계산용) — 타일 없이 방향만 계산
    provisional_info = _provisional_connection_info(map_specs, id_table)

    # 4. 타일 생성 (출구 방향 전달)
    map_tiles: dict[int, list[int]] = {}
    for ms in map_specs:
        mid  = id_table.get_id("maps", ms.name)
        seed = hash(f"{state['generation_id']}:{ms.name}") % (2**32)
        map_tiles[mid] = generate_map(ms, provisional_info.get(mid), seed)

    # 5. 최종 connection_info (실제 타일 기반 좌표 확인)
    connection_info = calculate_all_connection_info(map_specs, id_table, map_tiles)

    return {
        "map_specs": map_specs,
        "map_tiles": map_tiles,
        "connection_info": connection_info,
    }

def _provisional_connection_info(
    map_specs: list[MapSpec], id_table: IdTable
) -> dict[int, MapConnectionInfo]:
    """타일 없이 방향 기반 임시 connection_info 생성 (타일 생성 전 사용)."""
    name_to_spec = {m.name: m for m in map_specs}
    result = {}
    for spec in map_specs:
        mid = id_table.get_id("maps", spec.name)
        exits = []
        for tgt_name in spec.connects_to:
            tgt_spec = name_to_spec.get(tgt_name)
            if not tgt_spec: continue
            tgt_id = id_table.get_id("maps", tgt_name)
            src_dir, tgt_dir = determine_exit_direction(spec.type, tgt_spec.type)
            ex, ey = exit_direction_to_coord(src_dir, spec.width, spec.height)
            enx, eny = exit_direction_to_coord(tgt_dir, tgt_spec.width, tgt_spec.height)
            exits.append(ExitInfo(tgt_id, ex, ey, enx, eny))
        result[mid] = MapConnectionInfo(mid, spec.width//2, spec.height//2, exits)
    return result
```

---

## R22. 이벤트 좌표 중복 (P2)

event_planner가 두 이벤트를 같은 (x,y)에 배치하면 하나만 표시된다.

### 방지

event_planner 프롬프트에 좌표 사용 추적 규칙 추가:
```
## 이벤트 좌표 규칙
- 각 이벤트는 서로 다른 (x, y) 좌표를 사용해야 합니다.
- NPC들은 최소 2칸 이상 떨어져 배치하세요.
- 출구 transfer 이벤트의 좌표는 connection_info의 exit_x/exit_y를 정확히 사용하세요.
```

event_compiler에서 이벤트 좌표 중복 검출:
```python
def check_event_coordinate_conflicts(
    compiled_events: dict[int, list]
) -> list[str]:
    warnings = []
    for map_id, events in compiled_events.items():
        seen: set[tuple[int,int]] = set()
        for event in events:
            coord = (event.get("x", 0), event.get("y", 0))
            if coord in seen:
                warnings.append(
                    f"Map {map_id}: 이벤트 좌표 중복 {coord}"
                )
            seen.add(coord)
    return warnings
```

---

## event_planner에 connection_info 주입 방식

event_planner_prompt.py에서 각 맵의 connection_info를 구체적인 좌표로 주입:

```python
def _format_connection_info(
    map_spec: MapSpec,
    conn: MapConnectionInfo,
    id_to_name: dict[int, str],
) -> str:
    lines = [f"## {map_spec.name} 연결 정보"]
    lines.append(f"- 스폰 위치: ({conn.spawn_x}, {conn.spawn_y})")
    for exit_info in conn.exits:
        tgt_name = id_to_name.get(exit_info.target_map_id, f"Map{exit_info.target_map_id}")
        lines.append(
            f"- {tgt_name}으로 가는 출구: x={exit_info.exit_x}, y={exit_info.exit_y}"
        )
        lines.append(
            f"  (transfer 이벤트: target_map_id={exit_info.target_map_id}, "
            f"target_x={exit_info.entry_x}, target_y={exit_info.entry_y})"
        )
    return "\n".join(lines)
```

이 텍스트가 event_planner의 system prompt에 포함된다:
```
## 맵 연결 정보 (반드시 준수)
마을 연결 정보:
- 스폰 위치: (15, 15)
- 던전으로 가는 출구: x=15, y=29
  (transfer 이벤트: target_map_id=2, target_x=20, target_y=0)
```

event_planner LLM은 이 좌표를 DSL에 그대로 사용해야 한다.

---

## 테스트

```python
# agent/tests/generation/test_map_connectivity.py

def test_normalize_connections_adds_reverse():
    maps = [
        MapSpec(name="마을",   type="town",    connects_to=["던전"]),
        MapSpec(name="던전",   type="dungeon", connects_to=["보스 방"]),
        MapSpec(name="보스 방", type="boss",   connects_to=[]),
    ]
    result = normalize_connections(maps)
    names = {m.name: m for m in result}
    assert "마을" in names["던전"].connects_to      # 역방향 추가됨
    assert "던전" in names["보스 방"].connects_to   # 보스도 역방향 추가됨

def test_validate_connectivity_all_reachable():
    maps = normalize_connections([
        MapSpec(name="마을",   type="town",    connects_to=["던전"]),
        MapSpec(name="던전",   type="dungeon", connects_to=["보스 방"]),
        MapSpec(name="보스 방", type="boss",   connects_to=[]),
    ])
    assert validate_map_connectivity(maps) == []

def test_validate_connectivity_island_detected():
    maps = [
        MapSpec(name="마을",   type="town",    connects_to=["던전"]),
        MapSpec(name="던전",   type="dungeon", connects_to=[]),
        MapSpec(name="외딴 섬", type="dungeon", connects_to=[]),  # 연결 없음
    ]
    errors = validate_map_connectivity(maps)
    assert any("외딴 섬" in e for e in errors)

def test_exit_direction_town_to_dungeon():
    src_dir, tgt_dir = determine_exit_direction("town", "dungeon")
    assert src_dir == ExitDirection.SOUTH
    assert tgt_dir == ExitDirection.NORTH

def test_connection_info_exit_is_walkable(sample_tiles):
    """출구 좌표가 실제 walkable 타일인지 확인."""
    spec = MapSpec(name="마을", type="town", width=30, height=30, connects_to=["던전"])
    conn_info = calculate_all_connection_info([spec, ...], id_table, map_tiles)
    for exit_info in conn_info[1].exits:
        assert _is_walkable_at(sample_tiles, exit_info.exit_x, exit_info.exit_y, 30)
```
