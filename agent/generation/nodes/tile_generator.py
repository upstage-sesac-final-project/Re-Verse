import logging
import math
import random

from agent.generation.schemas import MapConnectionInfo, MapSpec
from agent.generation.state import GenerationState
from agent.utils.game_data_io import save_temp_data

logger = logging.getLogger(__name__)

# RPG Maker MZ Outside Tileset Constants (Auto-tiles & Static)
TILES = {
    "grass": 2816,  # Auto-tile: Grass
    "dirt": 2624,  # Auto-tile: Dirt/Path
    "water": 2048,  # Auto-tile: Deep Water
    "tree": 3584,  # Static: Tree
    "fence": 4048,  # Static: Fence
    "house_roof": 3216,  # Auto-tile: Roof
    "house_wall": 3664,  # Auto-tile: Wall
    "flower": 2820,  # Grass with small flowers
}


async def tile_generator_node(state: GenerationState) -> GenerationState:
    """E. 타일 생성기 노드: 알고리즘 기반 고도화된 맵 생성."""
    logger.info("--- NODE: tile_generator (Advanced) ---")
    map_specs = state["map_specs"]
    game_id = state["game_id"]

    connection_info = {}

    for spec_dict in map_specs:
        spec = MapSpec.model_validate(spec_dict)
        if spec.map_type == "town":
            tiles = _generate_advanced_town(spec)
        elif spec.map_type == "field":
            tiles = _generate_advanced_field(spec)
        else:
            tiles = _generate_simple_dungeon_tiles(spec)

        save_temp_data(game_id, "tiles", spec.map_id, tiles)
        connection_info[spec.map_id] = _extract_connection_info(spec, tiles).model_dump()

    return {
        **state,
        "map_tiles": {},  # 상태 다이어트
        "connection_info": connection_info,
        "completed_phases": ["tiles_generated"],
        "current_phase": "tiles_generated",
    }


def _generate_advanced_town(spec: MapSpec) -> list[int]:
    w, h = spec.width, spec.height
    size = w * h
    grid = [[TILES["grass"] for _ in range(w)] for _ in range(h)]

    # 1. 강(River) 생성
    if random.random() > 0.5:
        river_y = random.randint(h // 4, h * 3 // 4)
        for x in range(w):
            offset = int(math.sin(x * 0.5) * 2)
            y_pos = max(0, min(h - 1, river_y + offset))
            grid[y_pos][x] = TILES["water"]
            if y_pos + 1 < h:
                grid[y_pos + 1][x] = TILES["water"]

    # 2. 길(Road) 네트워크
    points = [spec.spawn_point]
    for ex in spec.exits:
        if ex.direction == "north":
            points.append([w // 2, 0])
        elif ex.direction == "south":
            points.append([w // 2, h - 1])
        elif ex.direction == "east":
            points.append([w - 1, h // 2])
        elif ex.direction == "west":
            points.append([0, h // 2])

    for i in range(len(points) - 1):
        _draw_path(grid, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])

    # 3. 집(Houses)
    house_count = random.randint(2, 4)
    attempts = 0
    while house_count > 0 and attempts < 30:
        attempts += 1
        hx, hy = random.randint(2, w - 5), random.randint(2, h - 5)
        can_build = True
        for dy in range(-1, 4):
            for dx in range(-1, 4):
                if grid[hy + dy][hx + dx] != TILES["grass"]:
                    can_build = False
                    break
        if can_build:
            grid[hy][hx] = TILES["house_roof"]
            grid[hy][hx + 1] = TILES["house_roof"]
            grid[hy + 1][hx] = TILES["house_roof"]
            grid[hy + 1][hx + 1] = TILES["house_roof"]
            grid[hy + 2][hx] = TILES["house_wall"]
            grid[hy + 2][hx + 1] = TILES["house_wall"]
            house_count -= 1

    # 4. 테두리 나무
    for x in range(w):
        if grid[0][x] == TILES["grass"]:
            grid[0][x] = TILES["tree"]
        if grid[h - 1][x] == TILES["grass"]:
            grid[h - 1][x] = TILES["tree"]
    for y in range(h):
        if grid[y][0] == TILES["grass"]:
            grid[y][0] = TILES["tree"]
        if grid[y][w - 1] == TILES["grass"]:
            grid[y][w - 1] = TILES["tree"]

    data = [0] * (size * 6)
    for y in range(h):
        for x in range(w):
            data[y * w + x] = grid[y][x]
            if grid[y][x] == TILES["grass"] and random.random() < 0.1:
                data[y * w + x] = TILES["flower"]
    return data


def _generate_advanced_field(spec: MapSpec) -> list[int]:
    w, h = spec.width, spec.height
    size = w * h
    data = [TILES["grass"]] * size + [0] * (size * 5)
    for i in range(size):
        if random.random() < 0.05:
            data[size + i] = TILES["tree"]
    return data


def _draw_path(grid, x1, y1, x2, y2):
    step_x = 1 if x2 > x1 else -1
    for x in range(x1, x2 + step_x, step_x):
        if grid[y1][x] != TILES["water"]:
            grid[y1][x] = TILES["dirt"]
    step_y = 1 if y2 > y1 else -1
    for y in range(y1, y2 + step_y, step_y):
        if grid[y][x2] != TILES["water"]:
            grid[y][x2] = TILES["dirt"]


def _generate_simple_dungeon_tiles(spec: MapSpec) -> list[int]:
    w, h = spec.width, spec.height
    size = w * h
    data = [0] * (size * 6)
    for i in range(size):
        data[i] = 2816
    return data


def _extract_connection_info(spec: MapSpec, data: list[int]) -> MapConnectionInfo:
    exit_points = {}
    for ex in spec.exits:
        if ex.direction == "north":
            exit_points[ex.to_map_id] = [spec.width // 2, 0]
        elif ex.direction == "south":
            exit_points[ex.to_map_id] = [spec.width // 2, spec.height - 1]
        elif ex.direction == "east":
            exit_points[ex.to_map_id] = [spec.width - 1, spec.height // 2]
        elif ex.direction == "west":
            exit_points[ex.to_map_id] = [0, spec.height // 2]
    return MapConnectionInfo(
        map_id=spec.map_id, spawn_point=spec.spawn_point, exit_points=exit_points
    )
