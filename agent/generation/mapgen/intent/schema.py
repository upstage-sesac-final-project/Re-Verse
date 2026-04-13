"""MapIntent — 사용자 쿼리에서 추출한 구조화된 맵 의도.

Phase 1(샘플 선택)과 Phase 2(타일 조립)가 공유하는 영구 자산이다.
- Phase 1: tileset_hint + raw_keywords로 룰 필터링.
- Phase 2: biome/structures를 오토타일·배치 규칙으로 변환 (tileset_hint 무시).
"""

from typing import Literal

from pydantic import BaseModel, Field


class MapIntent(BaseModel):
    """쿼리에서 뽑아낸 맵 생성 의도."""

    biome: list[str] = Field(
        default_factory=list,
        description="지형/생태계 키워드. 예: ['숲','바다','사막','설원','산악']",
    )
    structures: list[str] = Field(
        default_factory=list,
        description="구조물 키워드. 예: ['마을','성','신전','던전','상점']",
    )
    mood: list[str] = Field(
        default_factory=list,
        description="분위기 키워드. 예: ['평화로운','신비로운','어두운','웅장한']",
    )
    era: Literal["fantasy", "medieval", "modern", "sf", "mixed"] = Field(
        default="fantasy",
        description="시대/세계관. 'fantasy'가 기본.",
    )
    scale: Literal["small", "medium", "large", "world"] = Field(
        default="medium",
        description="원하는 맵 규모.",
    )
    tileset_hint: list[int] = Field(
        default_factory=list,
        description=(
            "Phase 1 룰 필터에 사용하는 타일셋 ID 화이트리스트. "
            "1=월드맵, 2=자연/야외, 3=건물 실내, 4=던전/지하, 5=현대 야외, 6=SF/현대 실내. "
            "비어 있으면 모든 타일셋 허용."
        ),
    )
    n_maps: int = Field(
        default=3,
        ge=1,
        le=10,
        description="반환할 맵 개수.",
    )
    raw_keywords: list[str] = Field(
        default_factory=list,
        description=(
            "쿼리에서 추출한 한국어 원시 키워드. 룰 필터의 태그 매칭에 직접 쓰인다. "
            "biome/structures/mood에 들어간 한국어 키워드를 모두 포함해도 무방."
        ),
    )

    def all_keywords(self) -> list[str]:
        """룰 필터가 사용하는 통합 키워드 리스트 (중복 제거, 순서 유지)."""
        seen: set[str] = set()
        out: list[str] = []
        for kw in self.biome + self.structures + self.mood + self.raw_keywords:
            if kw and kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out
