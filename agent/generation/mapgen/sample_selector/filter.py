"""룰 기반 후보 필터링.

map_metadata.json 전체를 메모리에 로드하고, MapIntent에 대해 점수를 매겨
상위 N개 후보를 반환한다.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from agent.generation.mapgen.intent.schema import MapIntent

_METADATA_PATH = Path(__file__).parents[1] / "data" / "map_metadata.json"

# 룰 점수 가중치 (PLAN.md §4.1)
W_TILESET = 2.0
W_TAG = 5.0
W_DESC = 1.0
W_SCALE = 1.5

DEFAULT_TOP_K = 30


class MapExit(TypedDict):
    coord: list[int]
    direction: str
    leads_to_id: int
    leads_to_name: str


class MapEntry(TypedDict):
    file_name: str
    display_name: str
    width: int
    height: int
    tileset_id: int
    tags: list[str]
    description: str
    exits: list[MapExit]


class ScoredEntry(TypedDict):
    score: float
    entry: MapEntry


@lru_cache(maxsize=1)
def load_metadata() -> list[MapEntry]:
    """map_metadata.json을 한 번만 로드해서 캐시한다."""
    raw = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
    return raw  # type: ignore[no-any-return]


def _scale_label(width: int, height: int) -> str:
    area = width * height
    if area >= 8000:
        return "world"
    if area >= 2500:
        return "large"
    if area >= 800:
        return "medium"
    return "small"


def _scale_match(intent_scale: str, w: int, h: int) -> float:
    label = _scale_label(w, h)
    if label == intent_scale:
        return 1.0
    # 인접 규모도 부분 점수
    order = ["small", "medium", "large", "world"]
    try:
        diff = abs(order.index(label) - order.index(intent_scale))
    except ValueError:
        return 0.0
    return max(0.0, 1.0 - 0.4 * diff)


def score_entry(intent: MapIntent, entry: MapEntry) -> float:
    """단일 맵에 대한 룰 점수."""
    keywords = intent.all_keywords()
    tag_set = set(entry["tags"])
    kw_set = set(keywords)

    # 1) 타일셋 매칭
    ts_score = 0.0
    if intent.tileset_hint:
        ts_score = 1.0 if entry["tileset_id"] in intent.tileset_hint else 0.0
    else:
        ts_score = 0.5  # 힌트 없으면 중립

    # 2) 태그 겹침 비율
    tag_score = 0.0
    if kw_set:
        overlap = len(tag_set & kw_set)
        tag_score = overlap / len(kw_set)

    # 3) 설명 키워드 부분일치
    desc = entry.get("description", "")
    desc_score = 0.0
    if keywords:
        hits = sum(1 for kw in keywords if kw and kw in desc)
        desc_score = min(1.0, hits / max(1, len(keywords)))

    # 4) 규모 매칭
    scale_score = _scale_match(intent.scale, entry["width"], entry["height"])

    return W_TILESET * ts_score + W_TAG * tag_score + W_DESC * desc_score + W_SCALE * scale_score


def rule_filter(intent: MapIntent, top_k: int = DEFAULT_TOP_K) -> list[ScoredEntry]:
    """룰 점수 기준 상위 top_k개 후보를 반환한다."""
    metadata = load_metadata()
    scored: list[ScoredEntry] = [{"score": score_entry(intent, e), "entry": e} for e in metadata]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
