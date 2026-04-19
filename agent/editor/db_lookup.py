"""게임 데이터 DB 조회 / fuzzy 매칭 공용 모듈.

Definition (Phase D+E+F 후속) 과 Reader 가 공유한다. 기존에는 reader.py 내부에
`_fuzzy_match` / `_find_candidates` 등이 private 로 갇혀 있었다.

노출하는 것:
- 상수: `PARAMS_INDEX`, `FUZZY_THRESHOLD`, `FUZZY_SUGGESTION_THRESHOLD`
- 저수준: `valid_items`, `fuzzy_match`, `find_candidates`, `build_id_name_map`,
  `get_field_value`, `get_numeric_value`
- 고수준: `lookup_by_name` — Definition 이 "이미 있음 / 없음 / 애매" 판정을
  한 번에 받기 위한 편의 함수

LLM 호출은 하지 않는다 (rule-base). 입력 정규화는 호출자 책임.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from agent.utils.game_data_io import read_game_json

# ── 상수 ──────────────────────────────────────────────────────────────────────

# RPG Maker MZ params 배열 인덱스 (enemy/actor 공통 8개 기본 스탯)
PARAMS_INDEX: dict[str, int] = {
    "maxhp": 0,
    "mhp": 0,
    "maxmp": 1,
    "mmp": 1,
    "atk": 2,
    "def": 3,
    "mat": 4,
    "mdf": 5,
    "agi": 6,
    "luk": 7,
}

# 한국어 스탯 라벨 → 표준 field_name 매핑 (Definition Step 1 value 파서 보조)
KO_STAT_ALIAS: dict[str, str] = {
    "hp": "maxhp",
    "mp": "maxmp",
    "체력": "maxhp",
    "마력": "maxmp",
    "공격": "atk",
    "공격력": "atk",
    "방어": "def",
    "방어력": "def",
    "마법공격력": "mat",
    "마법방어력": "mdf",
    "민첩": "agi",
    "민첩성": "agi",
    "운": "luk",
}

FUZZY_THRESHOLD = 0.6
FUZZY_SUGGESTION_THRESHOLD = 0.5

# ── 카테고리 ↔ 파일 ─────────────────────────────────────────────────────────

_CATEGORY_TO_FILE: dict[str, str] = {
    "actor": "Actors.json",
    "enemy": "Enemies.json",
    "item": "Items.json",
    "weapon": "Weapons.json",
    "armor": "Armors.json",
    "class": "Classes.json",
    "state": "States.json",
    "skill": "Skills.json",
}


def category_to_file(category: str) -> str | None:
    return _CATEGORY_TO_FILE.get((category or "").lower())


# ── 저수준 후보 탐색 ──────────────────────────────────────────────────────────


def valid_items(data: Any) -> list[dict]:
    """RPG Maker MZ JSON 배열에서 null 과 name 빈 슬롯 제거."""
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("name")]


def fuzzy_match(
    entity_name: str,
    items: list[dict],
    threshold: float = FUZZY_THRESHOLD,
) -> list[dict]:
    """SequenceMatcher 기반 유사도 매칭, 내림차순 반환."""
    if not entity_name:
        return []
    scored: list[tuple[float, dict]] = []
    q = entity_name.lower()
    for item in items:
        name = item.get("name", "")
        if not name:
            continue
        ratio = SequenceMatcher(None, q, name.lower()).ratio()
        if ratio >= threshold:
            scored.append((ratio, item))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [item for _, item in scored]


def find_candidates(entity_name: str, items: list[dict]) -> list[dict]:
    """ID 숫자 > exact > CI exact > prefix > fuzzy 우선순위."""
    if not entity_name:
        return []
    if entity_name.isdigit():
        by_id = [
            item for item in items if isinstance(item, dict) and item.get("id") == int(entity_name)
        ]
        if by_id:
            return by_id
    exact = [item for item in items if item.get("name") == entity_name]
    if exact:
        return exact
    ci = [item for item in items if item.get("name", "").lower() == entity_name.lower()]
    if ci:
        return ci
    prefix = [
        item for item in items if item.get("name", "").lower().startswith(entity_name.lower())
    ]
    if prefix:
        return prefix
    return fuzzy_match(entity_name, items)


def build_id_name_map(data: Any) -> dict[int, str]:
    if not isinstance(data, list):
        return {}
    return {item["id"]: item["name"] for item in data if isinstance(item, dict) and item.get("id")}


def get_field_value(entity: dict, field_name: str) -> tuple[Any, bool]:
    """엔티티에서 필드값 추출. dot notation / params 배열 접근 처리."""
    if "." in field_name:
        head, tail = field_name.split(".", 1)
        nested = entity.get(head)
        if isinstance(nested, dict):
            return get_field_value(nested, tail)
        return None, False
    if field_name in entity:
        return entity[field_name], True
    idx = PARAMS_INDEX.get(field_name.lower())
    if idx is not None:
        params = entity.get("params", [])
        if isinstance(params, list) and len(params) > idx:
            if isinstance(params[idx], (int, float)):
                return params[idx], True
    return None, False


def get_numeric_value(entity: dict, field_name: str) -> float | None:
    value, found = get_field_value(entity, field_name)
    if found and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


# ── 고수준: Definition 전용 조회 ──────────────────────────────────────────────


def lookup_by_name(
    game_id: str,
    category: str,
    name: str,
    *,
    threshold: float = FUZZY_THRESHOLD,
) -> dict:
    """카테고리 + 이름 으로 엔티티 조회. 결과 구조화.

    Args:
        game_id: 게임 ID
        category: "actor" | "enemy" | "item" | ... (대소문자 무관)
        name: 조회 이름
        threshold: fuzzy 매칭 임계값

    Returns:
        dict {
            "status": "found" | "not_found" | "ambiguous",
            "exact_match": dict | None,   # exact 또는 유일한 CI 매칭 시
            "candidates": list[dict],     # status="ambiguous" 일 때 복수. 그 외는 단일 / 빈 list
            "suggestions": list[dict],    # status="not_found" 시 유사 이름 top 3
            "category": str,              # 입력한 카테고리 (lowercase)
            "file": str | None,           # 파일명 (미지원 카테고리면 None)
        }
    """
    norm_cat = (category or "").lower()
    file_name = category_to_file(norm_cat)
    base: dict = {
        "status": "not_found",
        "exact_match": None,
        "candidates": [],
        "suggestions": [],
        "category": norm_cat,
        "file": file_name,
    }
    if not file_name or not name:
        return base

    try:
        data = read_game_json(game_id, file_name)
    except FileNotFoundError:
        return base
    except Exception:
        # 파일 손상 등은 조회 실패로 간주 (상위에서 hold 처리)
        return base

    items = valid_items(data)
    if not items:
        return base

    # 1) ID 숫자 / exact / CI exact → 단일 매칭 가능
    if name.isdigit():
        by_id = [item for item in items if isinstance(item, dict) and item.get("id") == int(name)]
        if by_id:
            return {**base, "status": "found", "exact_match": by_id[0]}

    exact = [item for item in items if item.get("name") == name]
    if len(exact) == 1:
        return {**base, "status": "found", "exact_match": exact[0]}
    if len(exact) > 1:
        return {**base, "status": "ambiguous", "candidates": exact}

    ci = [item for item in items if item.get("name", "").lower() == name.lower()]
    if len(ci) == 1:
        return {**base, "status": "found", "exact_match": ci[0]}
    if len(ci) > 1:
        return {**base, "status": "ambiguous", "candidates": ci}

    # 2) fuzzy → threshold 이상 여러 건이면 ambiguous, 단일이면 ambiguous 취급
    #    ("이미 비슷한 게 있어요" 신호 — Definition 이 already_exists 로 hold 낼 수 있게)
    fuzzy = fuzzy_match(name, items, threshold=threshold)
    if fuzzy:
        return {**base, "status": "ambiguous", "candidates": fuzzy[:5]}

    # 3) 완전히 새 이름. 단, 힌트용 suggestion 은 낮은 임계값으로 별도 계산
    suggestions = fuzzy_match(name, items, threshold=FUZZY_SUGGESTION_THRESHOLD)[:3]
    return {**base, "status": "not_found", "suggestions": suggestions}
