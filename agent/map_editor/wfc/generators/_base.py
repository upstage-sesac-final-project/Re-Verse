"""생성 알고리즘 공통 유틸."""

from __future__ import annotations

import random


def edge_point(
    width: int,
    height: int,
    edge: str,
    ratio: float,
) -> tuple[float, float]:
    """edge 이름 + 비율(0~1)로 맵 경계 좌표를 반환한다.

    edge: "top" | "bottom" | "left" | "right"
    ratio: 해당 edge 위에서의 위치 (0.0 = 왼쪽/위, 1.0 = 오른쪽/아래)
    """
    ratio = max(0.0, min(1.0, ratio))
    if edge == "top":
        return (ratio * (width - 1), 0.0)
    if edge == "bottom":
        return (ratio * (width - 1), float(height - 1))
    if edge == "left":
        return (0.0, ratio * (height - 1))
    if edge == "right":
        return (float(width - 1), ratio * (height - 1))
    # fallback: 중앙
    return (width / 2, height / 2)


def paint_circle(
    cells: set[tuple[int, int]],
    cx: float,
    cy: float,
    radius: int,
    width: int,
    height: int,
) -> None:
    """(cx, cy) 중심 반지름 radius의 원형 브러시로 cells에 추가한다."""
    ix, iy = int(round(cx)), int(round(cy))
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= r2 + radius:
                nx, ny = ix + dx, iy + dy
                if 0 <= nx < width and 0 <= ny < height:
                    cells.add((nx, ny))


def walk_path(
    start: tuple[float, float],
    end: tuple[float, float],
    n_steps: int,
    roughness: float,
    momentum: float,
    width: int,
    height: int,
    rng: random.Random,
) -> list[tuple[float, float]]:
    """start → end 사이를 구불구불하게 걷는 경로를 반환한다.

    roughness: 진폭 (클수록 구불구불)
    momentum:  관성 (클수록 완만한 곡선, 0이면 매 스텝 독립 노이즈)
    """
    sx, sy = start
    ex, ey = end

    # 주 이동 방향 (스텝당)
    ddx = (ex - sx) / max(n_steps, 1)
    ddy = (ey - sy) / max(n_steps, 1)

    # 수직 방향 단위벡터 (왼쪽 90° 회전)
    length = (ddx**2 + ddy**2) ** 0.5 or 1.0
    px, py = -ddy / length, ddx / length

    cx, cy = sx, sy
    vperp = 0.0
    path: list[tuple[float, float]] = [(cx, cy)]

    for _ in range(n_steps):
        cx += ddx
        cy += ddy

        noise = rng.gauss(0, roughness)
        vperp = vperp * momentum + noise * (1.0 - momentum)

        cx += vperp * px
        cy += vperp * py

        cx = max(0.0, min(width - 1, cx))
        cy = max(0.0, min(height - 1, cy))
        path.append((cx, cy))

    path.append((ex, ey))
    return path
