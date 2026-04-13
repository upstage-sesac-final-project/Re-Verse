"""GenerationState — Full Generation LangGraph 워크플로우의 공유 상태.

canonical: docs/The_world/full_generation_plan.md
"""

from typing import Any, TypedDict

from agent.generation.models import (
    GameQuestPlan,
    GameSpec,
    MapConnectionInfo,
    MapSpec,
    MapStoryScript,
)
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable


class GenerationState(TypedDict, total=False):
    # ── 입력 ─────────────────────────────────────────────
    user_input: str
    game_id: str
    generation_id: str
    options: dict[str, Any]  # 추가: playtime_minutes 등 설정 저장

    # ── B 노드 (asset_planner) 출력 ───────────────────────
    id_table: IdTable | None
    switch_table: SwitchTable | None
    generation_order: list[str]
    phase_limit: str | None  # "assets" | "maps" | None
    map_source: str | None  # "algorithmic" (기본, D+E) | "samples" (샘플맵 선택기)

    # ── A+C 노드 출력 ──────────────────────────────────────
    game_spec: GameSpec | None
    generated_assets: dict[str, Any]  # {"Actors.json": [...], ...}

    # ── D+E 노드 출력 ──────────────────────────────────────
    map_specs: list[MapSpec]
    map_tiles: dict[int, list[int]]  # map_id → flat 1D (width×height×6)
    connection_info: dict[int, MapConnectionInfo]

    # ── F 노드 (story_planner) 출력 ───────────────────────
    story_script: dict[int, MapStoryScript] | None  # map_id → MapStoryScript
    quest_plan: GameQuestPlan | None  # 퀘스트 계획 (story_planner 또는 fallback)

    # ── F-2 노드 (event_scaffolder) 출력 ──────────────────
    event_skeletons: dict[int, list]  # map_id → list[DslEvent] (scaffolded)

    # ── G+H 노드 출력 ─────────────────────────────────────
    event_dsl: dict[int, list]
    compiled_events: dict[int, list[dict]]

    # ── H 노드 출력 ────────────────────────────────────────
    final_project: dict[str, Any]  # 파일명 → JSON

    # ── I 노드 출력 ────────────────────────────────────────
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    retry_count: int

    # ── 체크포인트 ─────────────────────────────────────────
    completed_phases: list[str]
    error_phase: str | None
    error_message: str | None

    # ── J 노드 출력 ────────────────────────────────────────
    final_message: str
    is_success: bool
