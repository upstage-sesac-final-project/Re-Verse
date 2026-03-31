"""강/하천 생성기 — Random Walk with Momentum.

params:
    from_edge   : "top" | "bottom" | "left" | "right"
    to_edge     : 같은 형식
    from_ratio  : 출발 edge 위 위치 비율 (0.0~1.0)
    to_ratio    : 도착 edge 위 위치 비율
    width       : 강 너비 (타일 단위, 기본 3)
    roughness   : 구불거림 강도 (기본 1.2)
    momentum    : 관성 (기본 0.55, 낮을수록 더 구불구불)
"""

from __future__ import annotations

import random

from agent.map_editor.wfc.generators._base import edge_point, paint_circle, walk_path

_DEFAULT_ROUGHNESS = 1.2
_DEFAULT_MOMENTUM = 0.55


def generate(
    width: int,
    height: int,
    params: dict,
    rng: random.Random,
) -> set[tuple[int, int]]:
    from_edge = params.get("from_edge", "top")
    to_edge = params.get("to_edge", "bottom")
    from_ratio = float(params.get("from_ratio", 0.3))
    to_ratio = float(params.get("to_ratio", 0.5))
    river_width = int(params.get("width", 3))
    roughness = float(params.get("roughness", _DEFAULT_ROUGHNESS))
    momentum = float(params.get("momentum", _DEFAULT_MOMENTUM))

    start = edge_point(width, height, from_edge, from_ratio)
    end = edge_point(width, height, to_edge, to_ratio)

    # 스텝 수: 대각선 거리 기준
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    n_steps = max(int((dx**2 + dy**2) ** 0.5 * 1.5), width + height)

    path = walk_path(start, end, n_steps, roughness, momentum, width, height, rng)

    cells: set[tuple[int, int]] = set()
    radius = max(1, river_width // 2)
    for px, py in path:
        paint_circle(cells, px, py, radius, width, height)

    return cells
