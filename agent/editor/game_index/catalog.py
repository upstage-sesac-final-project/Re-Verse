"""GameIndex — 검색 API.

엔티티 이름으로 인덱스를 검색하는 함수들.
완전 일치 → 정규화 일치 → fuzzy 매칭 순서로 시도.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from agent.editor.game_index.index_builder import (
    EntityEntry,
    build_index,
    invalidate,
)

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.6


def _normalize(s: str) -> str:
    return s.strip().lower().replace(" ", "")


def find_entity(game_id: str, name: str, threshold: float = _FUZZY_THRESHOLD) -> list[EntityEntry]:
    """이름으로 전체 entity 파일에서 검색. 매칭되는 모든 결과 반환.

    완전 일치 우선, 없으면 fuzzy.
    """
    if not name:
        return []

    entries = build_index(game_id)
    target = _normalize(name)

    # 완전 일치
    exact = [e for e in entries if _normalize(e.name) == target]
    if exact:
        return exact

    # fuzzy
    scored: list[tuple[float, EntityEntry]] = []
    for e in entries:
        ratio = SequenceMatcher(None, target, _normalize(e.name)).ratio()
        if ratio >= threshold:
            scored.append((ratio, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored]


def find_in_file(
    game_id: str, filename: str, name: str, threshold: float = _FUZZY_THRESHOLD
) -> EntityEntry | None:
    """특정 파일에서 엔티티 검색."""
    if not name:
        return None
    entries = build_index(game_id)
    target = _normalize(name)

    # 완전 일치
    for e in entries:
        if e.file == filename and _normalize(e.name) == target:
            return e

    # fuzzy
    best, best_ratio = None, 0.0
    for e in entries:
        if e.file != filename:
            continue
        ratio = SequenceMatcher(None, target, _normalize(e.name)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = e
    return best if best_ratio >= threshold else None


def get_next_id(game_id: str, filename: str) -> int:
    """파일의 다음 사용 가능한 ID."""
    entries = build_index(game_id)
    used_ids = {e.id for e in entries if e.file == filename}
    if not used_ids:
        return 1
    max_id = max(used_ids)
    # 빈 슬롯이 있으면 그것 우선, 없으면 max+1
    for i in range(1, max_id + 1):
        if i not in used_ids:
            return i
    return max_id + 1


def invalidate_cache(game_id: str | None = None) -> None:
    """파일 변경 후 호출하여 인덱스 캐시 무효화."""
    invalidate(game_id)
