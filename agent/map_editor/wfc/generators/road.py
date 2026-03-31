"""길/도로 생성기 — Midpoint Displacement (완만한 곡선).

강보다 roughness가 낮고 momentum이 높아 더 직선에 가까운 곡선을 만든다.

params: river.py 와 동일 (roughness/momentum 기본값만 다름)
    from_edge, to_edge, from_ratio, to_ratio
    width     : 길 너비 (기본 2)
    roughness : 구불거림 (기본 0.5, 강보다 낮음)
    momentum  : 관성 (기본 0.82, 강보다 높음)
"""

from __future__ import annotations

import random

from agent.map_editor.wfc.generators._base import edge_point, paint_circle, walk_path

_DEFAULT_ROUGHNESS = 0.5
_DEFAULT_MOMENTUM = 0.82


def generate(
    width: int,
    height: int,
    params: dict,
    rng: random.Random,
) -> set[tuple[int, int]]:
    from_edge = params.get("from_edge", "top")
    to_edge = params.get("to_edge", "bottom")
    from_ratio = float(params.get("from_ratio", 0.6))
    to_ratio = float(params.get("to_ratio", 0.6))
    road_width = int(params.get("width", 2))
    roughness = float(params.get("roughness", _DEFAULT_ROUGHNESS))
    momentum = float(params.get("momentum", _DEFAULT_MOMENTUM))

    start = edge_point(width, height, from_edge, from_ratio)
    end = edge_point(width, height, to_edge, to_ratio)

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    n_steps = max(int((dx**2 + dy**2) ** 0.5 * 1.5), width + height)

    path = walk_path(start, end, n_steps, roughness, momentum, width, height, rng)

    cells: set[tuple[int, int]] = set()
    radius = max(0, road_width // 2)
    for px, py in path:
        paint_circle(cells, px, py, radius, width, height)

    return cells
