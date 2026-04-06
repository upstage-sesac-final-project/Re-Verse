# 맵 생성 상세 설계

> 관련 노드: D. 맵 설계사, E. 타일 생성기
> 위치: `agent/generation/mapgen/`

---

## 개요

맵 생성은 LLM이 하는 일(고수준 명세)과 알고리즘이 하는 일(타일 배치)로 명확히 분리된다.

```
LLM (map_designer.py)          알고리즘 (mapgen/)
──────────────────────         ─────────────────────────────
"마을이 있고 북쪽에 여관,      →   width=17, height=13 격자 생성
 동쪽에 상점, 남쪽에 출구"    →   여관 위치: (6~10, 2~4) 건물 타일
                              →   길 타일로 연결
                              →   출구 위치: (8, 12)
```

LLM은 **어떤 요소가 어디에 있어야 하는가** 만 결정한다.
타일 숫자 배열은 알고리즘이 결정론적으로 생성한다.

---

## MapSpec 구조 (D. 맵 설계사 출력)

```python
class LandmarkSpec(BaseModel):
    name: str                          # "여관", "상점", "마을 입구"
    landmark_type: str                 # "building", "exit", "decoration"
    position_hint: str                 # "north-center", "east", "south"
    npc: str | None = None            # NPC 이름 (이벤트 기획자에서 사용)

class ExitSpec(BaseModel):
    direction: str                     # "north", "south", "east", "west"
    to_map_id: int                    # 목적지 맵 ID
    label: str                        # "던전으로 가는 길"

class MapSpec(BaseModel):
    map_id: int
    name: str
    map_type: Literal["town", "dungeon", "boss", "field"]
    width: int                         # 30 고정 (town), 40 고정 (dungeon)
    height: int                        # 30 고정 (town), 30 고정 (dungeon)
    tileset_id: int
    bgm: str                           # "Town1", "Dungeon1"
    atmosphere: str                    # 이벤트 기획자에 전달하는 분위기 설명
    landmarks: list[LandmarkSpec]
    exits: list[ExitSpec]
    spawn_point: tuple[int, int]       # 플레이어 시작 좌표 (x, y)
```

---

## D. 맵 설계사 (map_designer.py)

LLM을 1회 호출해서 전체 맵 목록의 MapSpec을 한꺼번에 생성.

### LLM 프롬프트 구조

```
시스템:
당신은 RPG Maker MZ 맵 설계사입니다.
게임 스펙을 받아 각 맵의 고수준 명세를 JSON으로 출력하세요.

규칙:
- town 맵: width=30, height=30, tileset_id=1
- dungeon 맵: width=40, height=30, tileset_id=2
- boss 맵: width=20, height=20, tileset_id=2
- field 맵: width=40, height=30, tileset_id=1
※ 크기는 MAP_SIZE_BY_TYPE (rpgmaker_default_assets.md) 에서 하드코딩됨.
  map_designer가 이 값 이외를 생성하면 map_designer 노드에서 덮어씀.
- 각 맵은 반드시 다른 맵으로의 exit이 1개 이상 있어야 함
- spawn_point는 반드시 이동 가능한 타일이어야 함 (벽 근처 피할 것)
- landmark position_hint 허용값: "north", "south", "east", "west",
  "north-center", "south-center", "east-center", "west-center", "center"

입력:
{game_spec}

출력: MapSpec 배열 (JSON)
```

### 출력 예시

```json
[
  {
    "map_id": 1,
    "name": "출발 마을",
    "map_type": "town",
    "width": 30,
    "height": 30,
    "tileset_id": 1,
    "bgm": "Town1",
    "atmosphere": "평화롭고 따뜻한 중세 마을. 주민들이 몬스터 위협에 불안해한다.",
    "landmarks": [
      {"name": "여관", "landmark_type": "building", "position_hint": "north-center", "npc": "여관주인"},
      {"name": "무기상점", "landmark_type": "building", "position_hint": "east", "npc": "상인"},
      {"name": "마을_게시판", "landmark_type": "decoration", "position_hint": "center", "npc": null}
    ],
    "exits": [
      {"direction": "south", "to_map_id": 2, "label": "던전으로 가는 남쪽 길"}
    ],
    "spawn_point": [8, 6]
  }
]
```

---

## E. 타일 생성기 — 공통 구조

### 타일셋 ID 매핑

RPG Maker MZ 기본 타일셋 기준.

```python
# 마을 타일셋 (tileset_id=1, Exterior)
TOWN_TILES = {
    "grass":        2816,   # 잔디 (이동 가능)
    "dirt_path":    2624,   # 흙길 (이동 가능)
    "stone_path":   2576,   # 돌길 (이동 가능)
    "water":        4352,   # 물 (이동 불가)
    "tree":         3584,   # 나무 (이동 불가)
    "fence":        3456,   # 울타리 (이동 불가)
    "building_tl":  2050,   # 건물 타일 2×2 블록
    "building_tr":  2051,
    "building_bl":  2082,
    "building_br":  2083,
    "door":         2114,   # 문 (이동 가능, 이벤트 트리거)
    "well":         2370,   # 우물 (이동 불가, 장식)
    "border_wall":  2624,   # 외곽 벽
}

# 던전 타일셋 (tileset_id=2, Dungeon)
DUNGEON_TILES = {
    "floor":        2816,   # 바닥 (이동 가능)
    "wall":         2624,   # 벽 (이동 불가)
    "wall_top":     2576,   # 벽 상단 장식
    "door":         2818,   # 문
    "stairs_up":    2884,   # 위층 계단 (입구)
    "stairs_down":  2885,   # 아래층 계단 (출구, 다음 맵으로)
    "chest_tile":   2882,   # 상자 위치 표시
    "darkness":     0,      # 아무것도 없음
    "lava":         4416,   # 용암 (이동 불가, 장식)
}
```

### 타일 배열 구조 (6레이어)

RPG Maker MZ는 맵 데이터를 6개의 레이어로 쌓아 표현한다.

```
data 배열 = width × height × 6 개의 정수

인덱스 계산:
  layer_offset = layer_index × (width × height)
  tile_index   = layer_offset + (y × width) + x

레이어 0: 지형 기반 (바닥, 물 등)  ← 가장 중요
레이어 1: 지형 상단 (건물 지붕, 나무 위 등)
레이어 2: 장식 하단
레이어 3: 장식 상단
레이어 4: 그림자
레이어 5: 통행 불가 영역 (0=통행, 0 이외=통행불가)
```

```python
def make_empty_data(width: int, height: int) -> list[int]:
    return [0] * (width * height * 6)

def set_tile(data: list[int], x: int, y: int, width: int,
             layer: int, tile_id: int) -> None:
    idx = (layer * width * height) + (y * width) + x
    data[idx] = tile_id

def get_tile(data: list[int], x: int, y: int, width: int,
             layer: int) -> int:
    idx = (layer * width * height) + (y * width) + x
    return data[idx]
```

---

## E-1. 마을 생성기 (town_generator.py)

### 알고리즘: 격자형 건물 배치

```
1단계: 전체 잔디로 채우기
2단계: 외곽 울타리/나무 배치
3단계: 중앙 십자형 돌길 배치
4단계: 랜드마크 위치 계산 (position_hint → 실제 좌표)
5단계: 건물 타일 배치 (2×2 블록)
6단계: 건물들 사이 돌길로 연결
7단계: exits 위치에 출구 타일
8단계: 충돌 레이어(5) 설정
```

### position_hint → 좌표 변환

```python
# width/height를 동적으로 받아 비율 기반 계산 (30×30, 40×30 등 다양한 크기 지원)
def _hint_ratios(hint: str) -> tuple[float, float]:
    """position_hint → (x비율, y비율). 0.0~1.0."""
    return {
        "north":        (0.5, 0.1),
        "south":        (0.5, 0.9),
        "east":         (0.9, 0.5),
        "west":         (0.1, 0.5),
        "north-center": (0.5, 0.15),
        "south-center": (0.5, 0.85),
        "east-center":  (0.85, 0.5),
        "west-center":  (0.15, 0.5),
        "center":       (0.5, 0.5),
    }.get(hint, (0.5, 0.5))

def hint_to_coords(hint: str, width: int, height: int) -> tuple[int, int]:
    """position_hint를 실제 타일 좌표로 변환. 겹침 방지를 위해 약간의 랜덤 오프셋 추가."""
    rx, ry = _hint_ratios(hint)
    base_x = int(width * rx)
    base_y = int(height * ry)
    offset_x = random.randint(-2, 2)   # 큰 맵에서 더 넓은 오프셋
    offset_y = random.randint(-2, 2)
    x = max(2, min(width - 3, base_x + offset_x))
    y = max(2, min(height - 3, base_y + offset_y))
    return x, y
```

### 전체 구현 흐름

```python
def generate_town(spec: MapSpec, seed: int = 0) -> list[int]:
    random.seed(seed)
    w, h = spec.width, spec.height
    data = make_empty_data(w, h)

    # 1단계: 전체 잔디
    for y in range(h):
        for x in range(w):
            set_tile(data, x, y, w, 0, TOWN_TILES["grass"])

    # 2단계: 외곽 나무 (1타일 테두리)
    for x in range(w):
        set_tile(data, x, 0, w, 1, TOWN_TILES["tree"])
        set_tile(data, x, h - 1, w, 1, TOWN_TILES["tree"])
    for y in range(h):
        set_tile(data, 0, y, w, 1, TOWN_TILES["tree"])
        set_tile(data, w - 1, y, w, 1, TOWN_TILES["tree"])

    # 3단계: 중앙 돌길 (십자형)
    for x in range(1, w - 1):
        set_tile(data, x, h // 2, w, 0, TOWN_TILES["stone_path"])
    for y in range(1, h - 1):
        set_tile(data, w // 2, y, w, 0, TOWN_TILES["stone_path"])

    # 4~5단계: 랜드마크 배치
    building_positions = []
    for landmark in spec.landmarks:
        if landmark.landmark_type == "building":
            bx, by = hint_to_coords(landmark.position_hint, w, h)
            place_building(data, bx, by, w)
            building_positions.append((bx, by))

    # 6단계: 건물들을 길로 연결
    for bx, by in building_positions:
        connect_to_road(data, bx, by, w, h)

    # 7단계: 출구 타일
    for exit_spec in spec.exits:
        ex, ey = get_exit_position(exit_spec.direction, w, h)
        set_tile(data, ex, ey, w, 0, TOWN_TILES["dirt_path"])
        set_tile(data, ex, ey, w, 1, 0)  # 장애물 제거

    # 8단계: 통행 불가 설정 (tree, water, building 타일)
    set_passability(data, w, h)

    return data


def place_building(data: list[int], x: int, y: int, width: int) -> None:
    """2×2 건물 블록 배치"""
    set_tile(data, x,     y,     width, 1, TOWN_TILES["building_tl"])
    set_tile(data, x + 1, y,     width, 1, TOWN_TILES["building_tr"])
    set_tile(data, x,     y + 1, width, 1, TOWN_TILES["building_bl"])
    set_tile(data, x + 1, y + 1, width, 1, TOWN_TILES["building_br"])
    # 문은 건물 아래 중앙
    set_tile(data, x,     y + 2, width, 0, TOWN_TILES["door"])
```

### 건물 배치 규칙

- 건물 최소 간격: 3타일 (경로를 위한 공간)
- 외곽 1타일은 항상 나무/벽으로 유지
- 출구(exit)에는 반드시 도달 가능한 길 연결
- `spawn_point`는 중앙 교차로 근처로 자동 설정

---

## E-2. 던전 생성기 (dungeon_generator.py)

### 알고리즘: BSP 트리 (Binary Space Partitioning)

던전을 재귀적으로 반 분할해 방을 배치하고, 복도로 연결한다.

```
1단계: 전체 벽으로 채우기
2단계: BSP 트리 재귀 분할 (최소 방 크기 도달 시 중단)
3단계: 각 잎 노드에 방 생성 (랜덤 크기)
4단계: 형제 노드 쌍을 복도로 연결 (후위 순회)
5단계: 시작 지점(stairs_up), 끝 지점(stairs_down) 배치
6단계: 보물 상자 위치 마킹
7단계: 통행 불가 레이어 설정
```

### BSP 노드 구조

```python
from dataclasses import dataclass, field

@dataclass
class BSPNode:
    x: int
    y: int
    width: int
    height: int
    left: "BSPNode | None" = None
    right: "BSPNode | None" = None
    room: "Rect | None" = None       # 이 노드에 배치된 방

@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2
```

### BSP 분할 알고리즘

```python
MIN_ROOM_SIZE = 4   # 방 최소 크기
MIN_NODE_SIZE = 7   # 노드 최소 크기 (분할 중단 기준)


def split(node: BSPNode, depth: int = 0) -> None:
    """재귀 분할. depth로 무한 루프 방지."""
    if depth > 5:
        return
    if node.width < MIN_NODE_SIZE * 2 and node.height < MIN_NODE_SIZE * 2:
        return  # 더 이상 분할 불가

    # 가로/세로 중 더 긴 방향으로 분할
    split_horizontally = node.height > node.width

    if split_horizontally:
        # 세로 분할 (위/아래)
        split_y = random.randint(MIN_NODE_SIZE, node.height - MIN_NODE_SIZE)
        node.left  = BSPNode(node.x, node.y, node.width, split_y)
        node.right = BSPNode(node.x, node.y + split_y, node.width, node.height - split_y)
    else:
        # 가로 분할 (왼쪽/오른쪽)
        split_x = random.randint(MIN_NODE_SIZE, node.width - MIN_NODE_SIZE)
        node.left  = BSPNode(node.x, node.y, split_x, node.height)
        node.right = BSPNode(node.x + split_x, node.y, node.width - split_x, node.height)

    split(node.left, depth + 1)
    split(node.right, depth + 1)


def create_rooms(node: BSPNode) -> None:
    """각 잎 노드에 방 생성."""
    if node.left is None and node.right is None:
        # 잎 노드: 방 생성
        room_w = random.randint(MIN_ROOM_SIZE, node.width - 2)
        room_h = random.randint(MIN_ROOM_SIZE, node.height - 2)
        room_x = node.x + random.randint(1, node.width - room_w - 1)
        room_y = node.y + random.randint(1, node.height - room_h - 1)
        node.room = Rect(room_x, room_y, room_w, room_h)
        return

    if node.left:
        create_rooms(node.left)
    if node.right:
        create_rooms(node.right)


def get_room(node: BSPNode) -> Rect | None:
    """서브트리에서 방 하나를 반환 (복도 연결용)."""
    if node.room:
        return node.room
    left_room  = get_room(node.left)  if node.left  else None
    right_room = get_room(node.right) if node.right else None
    return left_room or right_room


def connect_rooms(node: BSPNode, data: list[int], width: int) -> None:
    """후위 순회로 형제 방들을 복도로 연결."""
    if node.left is None or node.right is None:
        return

    connect_rooms(node.left, data, width)
    connect_rooms(node.right, data, width)

    left_room  = get_room(node.left)
    right_room = get_room(node.right)
    if left_room and right_room:
        lx, ly = left_room.center
        rx, ry = right_room.center
        carve_corridor(data, lx, ly, rx, ry, width)


def carve_corridor(data: list[int], x1: int, y1: int,
                   x2: int, y2: int, width: int) -> None:
    """L자형 복도 굴착 (가로 먼저 → 세로)."""
    for x in range(min(x1, x2), max(x1, x2) + 1):
        set_tile(data, x, y1, width, 0, DUNGEON_TILES["floor"])
    for y in range(min(y1, y2), max(y1, y2) + 1):
        set_tile(data, x2, y, width, 0, DUNGEON_TILES["floor"])
```

### 전체 생성 흐름

```python
def generate_dungeon(spec: MapSpec, seed: int = 0) -> list[int]:
    random.seed(seed)
    w, h = spec.width, spec.height
    data = make_empty_data(w, h)

    # 1단계: 전체 벽으로 채우기
    for y in range(h):
        for x in range(w):
            set_tile(data, x, y, w, 0, DUNGEON_TILES["wall"])

    # 2~4단계: BSP 분할 + 방 생성 + 복도 연결
    root = BSPNode(1, 1, w - 2, h - 2)   # 외곽 1타일 여백
    split(root)
    create_rooms(root)

    # 방 타일 굴착
    def carve_rooms(node: BSPNode) -> None:
        if node.room:
            for dy in range(node.room.height):
                for dx in range(node.room.width):
                    set_tile(data, node.room.x + dx, node.room.y + dy,
                             w, 0, DUNGEON_TILES["floor"])
        if node.left:  carve_rooms(node.left)
        if node.right: carve_rooms(node.right)

    carve_rooms(root)
    connect_rooms(root, data, w)

    # 5단계: 계단 배치
    all_rooms = collect_rooms(root)
    start_room = all_rooms[0]     # 첫 번째 방 = 입구
    end_room   = all_rooms[-1]    # 마지막 방 = 출구

    sx, sy = start_room.center
    ex, ey = end_room.center
    set_tile(data, sx, sy, w, 0, DUNGEON_TILES["stairs_up"])
    set_tile(data, ex, ey, w, 0, DUNGEON_TILES["stairs_down"])

    # 6단계: 중간 방에 상자 마킹 (이벤트 기획자가 참조)
    for room in all_rooms[1:-1]:  # 시작/끝 제외
        if random.random() < 0.5:
            cx, cy = room.center
            set_tile(data, cx + 1, cy, w, 0, DUNGEON_TILES["chest_tile"])

    # 7단계: 통행 불가 레이어
    set_passability(data, w, h)

    return data


def collect_rooms(node: BSPNode) -> list[Rect]:
    """모든 방을 왼쪽→오른쪽 순서로 수집."""
    result = []
    if node.room:
        result.append(node.room)
    if node.left:
        result.extend(collect_rooms(node.left))
    if node.right:
        result.extend(collect_rooms(node.right))
    return result
```

---

## 스폰 포인트 자동 계산

```python
def calculate_spawn_point(spec: MapSpec, data: list[int]) -> tuple[int, int]:
    """
    map_designer가 제안한 spawn_point가 실제로 이동 가능한 타일인지 확인.
    불가능하면 가장 가까운 이동 가능 타일로 조정.
    """
    sx, sy = spec.spawn_point
    if is_walkable(data, sx, sy, spec.width):
        return sx, sy

    # BFS로 가장 가까운 이동 가능 타일 탐색
    from collections import deque
    q = deque([(sx, sy)])
    visited = {(sx, sy)}
    while q:
        x, y = q.popleft()
        if is_walkable(data, x, y, spec.width):
            return x, y
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited and 0 <= nx < spec.width:
                visited.add((nx, ny))
                q.append((nx, ny))

    return sx, sy  # fallback


def is_walkable(data: list[int], x: int, y: int, width: int) -> bool:
    return get_tile(data, x, y, width, layer=5) == 0
```

---

## 맵 연결점 (Connection Points) 계산

이벤트 기획자(F)가 transfer 이벤트 좌표를 정할 때 참조한다.

```python
@dataclass
class MapConnectionInfo:
    map_id: int
    spawn_point: tuple[int, int]    # 이 맵에 도착할 때 플레이어 위치
    exit_points: dict[int, tuple[int, int]]   # to_map_id → 출구 타일 좌표

def extract_connection_info(spec: MapSpec, data: list[int]) -> MapConnectionInfo:
    exit_points = {}
    for exit_spec in spec.exits:
        ex, ey = get_exit_position(exit_spec.direction, spec.width, spec.height)
        exit_points[exit_spec.to_map_id] = (ex, ey)

    return MapConnectionInfo(
        map_id=spec.map_id,
        spawn_point=calculate_spawn_point(spec, data),
        exit_points=exit_points,
    )
```

이 정보가 이벤트 기획자에게 전달되어:
- "마을 맵 출구는 (8, 12)이다"
- "던전 맵 입구(spawn)는 (10, 13)이다"

→ transfer 이벤트: `to_x: 10, to_y: 13` 으로 정확히 생성

---

## 테스트 전략

```python
# tests/generation/test_tile_generator.py

def test_town_all_tiles_placed():
    spec = make_town_spec()
    data = generate_town(spec, seed=42)
    # 배열 크기 확인
    assert len(data) == spec.width * spec.height * 6

def test_town_exits_are_walkable():
    spec = make_town_spec()
    data = generate_town(spec, seed=42)
    for exit_spec in spec.exits:
        ex, ey = get_exit_position(exit_spec.direction, spec.width, spec.height)
        assert is_walkable(data, ex, ey, spec.width), \
            f"출구 ({ex}, {ey})가 이동 불가 타일"

def test_dungeon_start_reachable_from_end():
    spec = make_dungeon_spec()
    data = generate_dungeon(spec, seed=42)
    sx, sy = get_stairs_up_position(data, spec.width)
    ex, ey = get_stairs_down_position(data, spec.width)
    assert bfs_reachable(data, sx, sy, ex, ey, spec.width), \
        "계단 사이가 연결되지 않음"

def test_dungeon_no_isolated_rooms():
    """모든 방이 복도로 연결되어 있는지 BFS로 검증."""
    spec = make_dungeon_spec()
    data = generate_dungeon(spec, seed=99)
    walkable_tiles = find_all_walkable(data, spec.width, spec.height)
    sx, sy = get_stairs_up_position(data, spec.width)
    reachable = bfs_all_reachable(data, sx, sy, spec.width)
    assert walkable_tiles == reachable, "도달 불가능한 방 존재"

def test_spawn_point_is_valid():
    spec = make_town_spec()
    data = generate_town(spec, seed=7)
    spawn = calculate_spawn_point(spec, data)
    assert is_walkable(data, *spawn, spec.width)
```

---

## 생성 결과 예시 (15×10 던전)

```
W W W W W W W W W W W W W W W
W . . . . W W W . . . W W W W
W . . . . W W W . . . W W W W
W . . . . . . . . . . W W W W
W W W . W W W W W . W W W W W
W W W . W . . . W . W . . . W
W W W . W . ↑  . W . W . . . W
W W W . . . . . . . W . . . W
W W W W W W W . W W W W W W W
W W W W W W W ↓ W W W W W W W

↑ = 계단 (입구), ↓ = 계단 (출구), . = 바닥, W = 벽
```

---

## 참고 링크

- DSL 명세: `docs/The_world/dsl_specification.md`
- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- RPG Maker MZ 타일셋 참조: `docs/rpgmaker/`
