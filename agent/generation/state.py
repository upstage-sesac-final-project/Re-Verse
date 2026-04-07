from operator import add
from typing import Annotated, Any, TypedDict


class GenerationState(TypedDict, total=False):
    # ── 입력 ────────────────────────────────────────────────
    user_input: str  # 사용자 원본 입력 (예: "중세 판타지 게임 만들어줘")
    game_id: str  # 생성될 게임의 고유 ID
    generation_id: str  # 생성 프로세스 ID

    # ── A. 기획자 (game_designer) 출력 ──────────────────────
    # 제목, 스토리, 캐릭터, 맵 목록 등 고수준 설계도
    game_spec: dict | None

    # ── B. 설계사 (asset_planner) 출력 ──────────────────────
    id_table: dict | None  # IdTable 객체 (registry/id_table.py)
    switch_table: dict | None  # SwitchTable 객체 (registry/switch_table.py)
    generation_order: list[str]  # 생성 순서
    phase_limit: str | None  # "assets" | "maps" | None (테스트/부분 생성용)

    # ── C. 에셋 생성 (asset_generator) 출력 ─────────────────
    # 파일명 -> RPG Maker MZ JSON 데이터 (dict)
    generated_assets: dict[str, Any]

    # ── D+E. 맵 설계사 + 타일 생성기 출력 ───────────────────
    map_specs: list[dict]  # 상세 MapSpec 리스트
    map_tiles: dict[int, list[int]]  # map_id -> flat 1D 타일 배열
    connection_info: dict[int, dict]  # map_id -> MapConnectionInfo

    # ── F+G. 이벤트 기획자 + 컴파일러 출력 ──────────────────
    event_dsl: dict[int, list]  # map_id -> DSL 이벤트 리스트
    compiled_events: dict[int, list]  # map_id -> RPG Maker 커맨드 배열

    # ── H. 통합기 (integrator) 출력 ────────────────────────
    # 최종 조립된 파일들 (System.json, MapInfos.json, Map001.json 등)
    final_project: dict[str, Any]

    # ── I. 검증기 (generation_validator) 출력 ───────────────
    validation_passed: bool
    validation_errors: Annotated[list[str], add]
    validation_warnings: Annotated[list[str], add]
    retry_count: int

    # ── J. 응답기 (generation_responder) 출력 ───────────────
    final_message: str  # 사용자에게 전달할 한국어 결과 메시지
    is_success: bool  # 전체 성공 여부

    # ── 상태 관리 및 체크포인트 ─────────────────────────────
    completed_phases: Annotated[list[str], add]
    current_phase: str
    error_phase: str | None
    error_message: str | None

    # WebSocket 진행률 보고용
    progress_percentage: int
