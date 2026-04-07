"""GenerationState — The World 파이프라인 공유 상태."""

from typing import TypedDict


class GenerationState(TypedDict, total=False):
    # ── 입력 ──
    user_prompt: str  # 사용자 원본 요청
    game_id: str  # 대상 게임 ID

    # ── GameDesigner 출력 ──
    world_spec: dict  # WorldSpec (세계관, 파티, 적, 맵 등)

    # ── AssetPlanner 출력 ──
    id_table: dict  # IdTable (이름→ID 매핑)
    asset_counts: dict  # Architect에게 전달할 에셋 개수

    # ── Architect 출력 ──
    game_blueprint: dict  # GameBlueprint (창작 콘텐츠)

    # ── Builder 출력 ──
    generated_files: list[str]  # 생성된 JSON 파일 목록
    build_errors: list[str]  # 빌드 중 발생한 오류

    # ── Validator 출력 ──
    validation_results: list
    validation_summary: str
    success: bool
    retry_count: int

    # ── 최종 출력 ──
    world_summary: str  # 사용자에게 보여줄 생성 결과 요약
