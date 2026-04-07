"""던전 타일 생성기 — BSP 트리 알고리즘.

canonical: docs/The_world/map_generation.md §E-2
"""

import random
from dataclasses import dataclass, field

from agent.generation.mapgen.tile_constants import (
    DUNGEON_IMPASSABLE,
    DUNGEON_TILES,
    make_empty_data,
    set_passability,
    set_tile,
)
from agent.generation.models import MapSpec

MIN_ROOM_SIZE = 4
MIN_NODE_SIZE = 7


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass
class BSPNode:
    x: int
    y: int
    width: int
    height: int
    left: "BSPNode | None" = field(default=None, repr=False)
    right: "BSPNode | None" = field(default=None, repr=False)
    room: "Rect | None" = None


def _split(node: BSPNode, depth: int = 0) -> None:
    """재귀 분할. depth > 5이면 중단."""
    if depth > 5:
        return
    can_split_h = node.height >= MIN_NODE_SIZE * 2
    can_split_v = node.width >= MIN_NODE_SIZE * 2
    if not can_split_h and not can_split_v:
        return

    # 더 긴 방향으로 분할
    split_horizontally = (
        (node.height > node.width) if (can_split_h and can_split_v) else can_split_h
    )

    if split_horizontally:
        split_y = random.randint(MIN_NODE_SIZE, node.height - MIN_NODE_SIZE)
        node.left = BSPNode(node.x, node.y, node.width, split_y)
        node.right = BSPNode(node.x, node.y + split_y, node.width, node.height - split_y)
    else:
        split_x = random.randint(MIN_NODE_SIZE, node.width - MIN_NODE_SIZE)
        node.left = BSPNode(node.x, node.y, split_x, node.height)
        node.right = BSPNode(node.x + split_x, node.y, node.width - split_x, node.height)

    _split(node.left, depth + 1)
    _split(node.right, depth + 1)


def _create_rooms(node: BSPNode) -> None:
    """각 잎 노드에 방 생성."""
    if node.left is None and node.right is None:
        max_rw = max(MIN_ROOM_SIZE, node.width - 2)
        max_rh = max(MIN_ROOM_SIZE, node.height - 2)
        room_w = random.randint(MIN_ROOM_SIZE, max_rw)
        room_h = random.randint(MIN_ROOM_SIZE, max_rh)
        room_x = node.x + random.randint(1, max(1, node.width - room_w - 1))
        room_y = node.y + random.randint(1, max(1, node.height - room_h - 1))
        node.room = Rect(room_x, room_y, room_w, room_h)
        return
    if node.left:
        _create_rooms(node.left)
    if node.right:
        _create_rooms(node.right)


def _get_room(node: BSPNode) -> Rect | None:
    if node.room:
        return node.room
    lr = _get_room(node.left) if node.left else None
    rr = _get_room(node.right) if node.right else None
    return lr or rr


def _carve_rooms(node: BSPNode, data: list[int], width: int, height: int) -> None:
    if node.room:
        for dy in range(node.room.height):
            for dx in range(node.room.width):
                set_tile(
                    data,
                    node.room.x + dx,
                    node.room.y + dy,
                    width,
                    height,
                    0,
                    DUNGEON_TILES["floor"],
                )
    if node.left:
        _carve_rooms(node.left, data, width, height)
    if node.right:
        _carve_rooms(node.right, data, width, height)


def _carve_corridor(
    data: list[int], x1: int, y1: int, x2: int, y2: int, width: int, height: int
) -> None:
    """L자형 복도 (가로 → 세로)."""
    for x in range(min(x1, x2), max(x1, x2) + 1):
        set_tile(data, x, y1, width, height, 0, DUNGEON_TILES["floor"])
    for y in range(min(y1, y2), max(y1, y2) + 1):
        set_tile(data, x2, y, width, height, 0, DUNGEON_TILES["floor"])


def _connect_rooms(node: BSPNode, data: list[int], width: int, height: int) -> None:
    """후위 순회로 형제 방들을 복도로 연결."""
    if node.left is None or node.right is None:
        return
    _connect_rooms(node.left, data, width, height)
    _connect_rooms(node.right, data, width, height)
    lr = _get_room(node.left)
    rr = _get_room(node.right)
    if lr and rr:
        lx, ly = lr.center
        rx, ry = rr.center
        _carve_corridor(data, lx, ly, rx, ry, width, height)


def _collect_rooms(node: BSPNode) -> list[Rect]:
    """모든 방을 왼쪽→오른쪽 순서로 수집."""
    result: list[Rect] = []
    if node.room:
        result.append(node.room)
    if node.left:
        result.extend(_collect_rooms(node.left))
    if node.right:
        result.extend(_collect_rooms(node.right))
    return result


def generate_dungeon(spec: MapSpec, seed: int = 0) -> list[int]:
    """던전 타일 데이터 생성. 반환: flat 1D list[int] (width×height×6)."""
    random.seed(seed if seed else spec.map_id + 100)
    w, h = spec.width, spec.height
    data = make_empty_data(w, h)

    # 1단계: 전체 벽
    for y in range(h):
        for x in range(w):
            set_tile(data, x, y, w, h, 0, DUNGEON_TILES["wall"])

    # 2~4단계: BSP 분할 + 방 생성 + 복도 연결
    root = BSPNode(1, 1, w - 2, h - 2)
    _split(root)
    _create_rooms(root)
    _carve_rooms(root, data, w, h)
    _connect_rooms(root, data, w, h)

    # 5단계: 계단 배치
    all_rooms = _collect_rooms(root)
    if not all_rooms:
        # fallback: 최소 1개 방
        cx, cy = w // 2, h // 2
        for dy in range(3):
            for dx in range(3):
                set_tile(data, cx + dx - 1, cy + dy - 1, w, h, 0, DUNGEON_TILES["floor"])
        all_rooms = [Rect(cx - 1, cy - 1, 3, 3)]

    start_room = all_rooms[0]
    end_room = all_rooms[-1]
    sx, sy = start_room.center
    ex, ey = end_room.center
    set_tile(data, sx, sy, w, h, 0, DUNGEON_TILES["stairs_up"])
    set_tile(data, ex, ey, w, h, 0, DUNGEON_TILES["stairs_down"])

    # 6단계: 중간 방에 상자 마킹
    for room in all_rooms[1:-1]:
        if random.random() < 0.5:
            cx, cy = room.center
            if cx + 1 < w - 1:
                set_tile(data, cx + 1, cy, w, h, 0, DUNGEON_TILES["chest_tile"])

    # 7단계: 통행 불가 레이어
    set_passability(data, w, h, DUNGEON_IMPASSABLE, layer_check=0)

    return data
