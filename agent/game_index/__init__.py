"""GameIndex — RPG Maker MZ 게임 데이터의 결정론적 인덱스/검색 레이어.

기존 RAG 벡터 검색 + SequenceMatcher 조합을 대체.
- 게임 데이터 파일을 스캔하여 (file, id, name, kind) 인덱스 생성
- 이름으로 엔티티를 빠르고 정확하게 검색
- System.json 타입 배열, 엔티티 참조 ID 해소
"""

from agent.game_index.catalog import (
    EntityEntry,
    find_entity,
    find_in_file,
    get_next_id,
    invalidate_cache,
)
from agent.game_index.index_builder import build_index
from agent.game_index.ref_resolver import resolve_entity_ref, resolve_system_type

__all__ = [
    "EntityEntry",
    "build_index",
    "find_entity",
    "find_in_file",
    "get_next_id",
    "invalidate_cache",
    "resolve_entity_ref",
    "resolve_system_type",
]
