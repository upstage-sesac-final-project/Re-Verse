"""Intent enum — Phase C 에서 도입.

기존 한국어 literal("게임_요소_생성" 등) 은 모호한 분기를 낳았다:
- "게임_요소_생성" 하나로 object/event 를 뭉쳐둠 → definition 에서 다시 분기
- router 에서 확정한 "조회" 가 reader 의 list vs game_overview 를 못 가름

본 enum 은 YB.md 1-7 카테고리 표를 정본으로 삼아 9 개 값으로 분리한다.
`clarification_needed` 는 YB.md 원문에는 없지만 빈 입력 / 저신뢰도 fallback
용으로 router 단에서 필요하여 추가했다 (Phase D 에서 hold 메커니즘으로
대체 가능성 검토 예정).
"""

from __future__ import annotations

from enum import StrEnum


class IntentValue(StrEnum):
    # definition 경로
    OBJECT_CREATE = "object_create"
    OBJECT_UPDATE = "object_update"
    EVENT_CREATE = "event_create"
    EVENT_UPDATE = "event_update"

    # reader 경로
    QUERY = "query"
    GAME_OVERVIEW = "game_overview"

    # terminal
    MULTI_INTENT = "multi_intent"
    OUT_OF_SCOPE = "out_of_scope"
    SMALL_TALK = "small_talk"
    CLARIFICATION_NEEDED = "clarification_needed"


# ── 카테고리 집합 (routing.py 에서 사용) ─────────────────────────
DEFINITION_INTENTS: frozenset[str] = frozenset(
    {
        IntentValue.OBJECT_CREATE,
        IntentValue.OBJECT_UPDATE,
        IntentValue.EVENT_CREATE,
        IntentValue.EVENT_UPDATE,
    }
)

READER_INTENTS: frozenset[str] = frozenset(
    {
        IntentValue.QUERY,
        IntentValue.GAME_OVERVIEW,
    }
)

TERMINAL_INTENTS: frozenset[str] = frozenset(
    {
        IntentValue.MULTI_INTENT,
        IntentValue.OUT_OF_SCOPE,
        IntentValue.SMALL_TALK,
        IntentValue.CLARIFICATION_NEEDED,
    }
)

ACTION_INTENTS: frozenset[str] = DEFINITION_INTENTS | READER_INTENTS


def is_terminal(intent: str) -> bool:
    return intent in TERMINAL_INTENTS


def is_event_intent(intent: str) -> bool:
    return intent in (IntentValue.EVENT_CREATE, IntentValue.EVENT_UPDATE)
