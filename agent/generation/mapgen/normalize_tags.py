"""map_metadata 태그 정규화.

사용법:
    python -m agent.generation.mapgen.normalize_tags

agent/generation/mapgen/data/map_metadata.backup.json + tag_aliases.json 을 읽어
agent/generation/mapgen/data/map_metadata.json 에 정규화 결과를 저장한다.
"""

import json
from collections import Counter
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
SOURCE = _DATA_DIR / "map_metadata.backup.json"
ALIASES = _DATA_DIR / "tag_aliases.json"
TARGET = _DATA_DIR / "map_metadata.json"


def build_reverse_map(aliases: dict) -> dict[str, str]:
    """동의어 → canonical 역방향 매핑. _comment 같은 메타 키는 제외."""
    rev: dict[str, str] = {}
    for canonical, synonyms in aliases.items():
        if canonical.startswith("_"):
            continue
        for syn in synonyms:
            if syn in rev:
                raise ValueError(f"동의어 중복: {syn} → {rev[syn]} vs {canonical}")
            rev[syn] = canonical
    return rev


def normalize_tags(tags: list[str], reverse: dict[str, str]) -> list[str]:
    """태그 리스트 정규화 + 순서 유지 중복 제거."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        canonical = reverse.get(t, t)
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    reverse = build_reverse_map(aliases)

    before_counter: Counter[str] = Counter(t for e in data for t in e["tags"])
    changed_maps = 0
    for entry in data:
        new_tags = normalize_tags(entry["tags"], reverse)
        if new_tags != entry["tags"]:
            changed_maps += 1
        entry["tags"] = new_tags

    after_counter: Counter[str] = Counter(t for e in data for t in e["tags"])

    TARGET.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"입력: {SOURCE.name} ({len(data)}개 맵)")
    print(f"동의어 매핑: {len(reverse)}개")
    print(f"변경된 맵: {changed_maps}개")
    print(f"고유 태그: {len(before_counter)} → {len(after_counter)}")
    print(f"출력: {TARGET}")


if __name__ == "__main__":
    main()
