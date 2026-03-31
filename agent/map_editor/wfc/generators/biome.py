"""지형 패치 생성기 — Voronoi 기반.

맵에 자연스럽게 분포된 지형 패치(모래사막, 눈밭, 풀숲 등)를 생성한다.

Voronoi 방식:
  1. "활성" 씨앗 N개 + "배경" 씨앗 M개를 랜덤 배치
  2. 각 셀 → 가장 가까운 씨앗이 "활성"이면 biome 타일

params:
    coverage  : 맵 전체 대비 biome 비율 (0.0~1.0, 기본 0.3)
    n_patches : 패치 덩어리 수 (기본 auto)
    clustered : True면 씨앗이 뭉쳐서 큰 패치, False면 분산 (기본 True)
"""

from __future__ import annotations

import random


def generate(
    width: int,
    height: int,
    params: dict,
    rng: random.Random,
) -> set[tuple[int, int]]:
    coverage = float(params.get("coverage", 0.3))
    clustered = bool(params.get("clustered", True))

    total = width * height
    # 활성 씨앗 수: coverage에 비례, 최소 1
    n_active = max(1, int(total * coverage / 25))
    # 배경 씨앗: 활성의 2배 (배경이 더 많아야 경계가 자연스러움)
    n_bg = max(2, n_active * 2)

    if clustered:
        # 활성 씨앗을 1~2개 중심 주변에 뭉침 → 큰 덩어리 패치
        n_centers = max(1, n_active // 3)
        centers = [
            (rng.uniform(0.15, 0.85) * width, rng.uniform(0.15, 0.85) * height)
            for _ in range(n_centers)
        ]
        spread = min(width, height) * 0.25

        active_seeds: list[tuple[float, float]] = []
        for _ in range(n_active):
            cx, cy = rng.choice(centers)
            x = rng.gauss(cx, spread)
            y = rng.gauss(cy, spread)
            active_seeds.append(
                (
                    max(0, min(width - 1, x)),
                    max(0, min(height - 1, y)),
                )
            )
    else:
        # 활성 씨앗 균일 분산
        active_seeds = [
            (rng.uniform(0, width - 1), rng.uniform(0, height - 1)) for _ in range(n_active)
        ]

    bg_seeds: list[tuple[float, float]] = [
        (rng.uniform(0, width - 1), rng.uniform(0, height - 1)) for _ in range(n_bg)
    ]

    all_seeds = active_seeds + bg_seeds
    active_set = set(range(n_active))  # 인덱스 기준

    cells: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            # 가장 가까운 씨앗 찾기
            min_dist = float("inf")
            nearest_idx = 0
            for i, (sx, sy) in enumerate(all_seeds):
                d = (x - sx) ** 2 + (y - sy) ** 2
                if d < min_dist:
                    min_dist = d
                    nearest_idx = i
            if nearest_idx in active_set:
                cells.add((x, y))

    return cells
