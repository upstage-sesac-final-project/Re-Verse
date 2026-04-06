"""GenerationState — Full Generation LangGraph 워크플로우의 공유 상태.

canonical: docs/The_world/full_generation_plan.md
"""

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from agent.generation.models import GameSpec, MapConnectionInfo, MapSpec
    from agent.generation.registry.id_table import IdTable
    from agent.generation.registry.switch_table import SwitchTable


class GenerationState(TypedDict, total=False):
    # ── 입력 ─────────────────────────────────────────────
    user_input: str
    game_id: str
    generation_id: str

    # ── B 노드 (asset_planner) 출력 ───────────────────────
    id_table: "IdTable | None"
    switch_table: "SwitchTable | None"
    generation_order: list[str]
    phase_limit: "str | None"  # "assets" | "maps" | None

    # ── A+C 노드 출력 ──────────────────────────────────────
    game_spec: "GameSpec | None"
    generated_assets: dict[str, Any]  # {"Actors.json": [...], ...}

    # ── D+E 노드 출력 ──────────────────────────────────────
    map_specs: "list[MapSpec]"
    map_tiles: dict[int, list[int]]  # map_id → flat 1D (width×height×6)
    connection_info: "dict[int, MapConnectionInfo]"

    # ── F+G 노드 출력 ──────────────────────────────────────
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
    error_phase: "str | None"
    error_message: "str | None"

    # ── J 노드 출력 ────────────────────────────────────────
    final_message: str
    is_success: bool
