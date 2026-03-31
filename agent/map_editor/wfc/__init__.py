"""Feature 기반 맵 자동 생성 모듈.

LLM이 feature spec(강/길/지형 의미)을 결정하면,
알고리즘이 종류에 맞게 자연스러운 타일을 채운다.

feature kind → 알고리즘:
    river / stream  → Random Walk (구불구불한 강)
    road / path     → Random Walk (완만한 길)
    biome / terrain → Voronoi (자연스러운 지형 패치)
    fill / rect     → Rectangle (실내 방, 고정 구역)
"""

from agent.map_editor.wfc.features import apply_features
from agent.map_editor.wfc.painter import generate_map_from_zones

__all__ = ["apply_features", "generate_map_from_zones"]
