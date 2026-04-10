"""new-agent AgentState — 얇은 state 정의.

기존 AgentState 의 drift 문제를 원천 방지한다.
모든 필드는 실제로 노드가 읽고 쓰는 것만 선언.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict


class AgentState(TypedDict, total=False):
    # ── 입력 ──
    user_input: str
    game_id: str
    conversation_history: list[dict]  # [{"role": "user"|"assistant", "content": str}]

    # ── intake 출력 ──
    kind: Literal["actionable", "chat", "out_of_scope", "need_more_info"]
    resolved_input: str
    operation_tuples: list[dict]
    clarification_question: str | None

    # ── planner 출력 ──
    execution_plan: list[dict]
    plan_meta: dict  # {op_index: [step_ids]}

    # ── profiler 출력 (execution_plan 내 target_info 가 갱신됨) ──
    # profiler 는 execution_plan 을 그대로 업데이트하므로 별도 필드 없음

    # ── executor 출력 ──
    changes_log: Annotated[list, add]  # 누적
    modified_file_paths: list[str]
    backup_paths: dict

    # ── validator 출력 ──
    success: bool
    retry_count: int
    validation_summary: str

    # ── 최종 응답 ──
    final_response: str
