"""AgentState — LangGraph 워크플로우의 공유 상태."""

from operator import add
from typing import Annotated, Literal, TypedDict


def _merge_dict(left: dict, right: dict) -> dict:
    """dict 병합 reducer. right가 비어 있으면 left를 그대로 유지한다."""
    if not right:
        return left
    return {**left, **right}


class AgentState(TypedDict, total=False):
    # ── 입력 ────────────────────────────────────────────────
    user_input: str  # 사용자 원본 입력
    game_id: str  # 수정 대상 게임 ID (예: "game_001")

    # ── 1단계 Router ────────────────────────────────────────
    intent: Literal[
        "게임_요소_생성",
        "게임_요소_수정",
        "게임_요소_조회",
        "추가_정보_필요",
        "복합_의도",
        "일반_대화",
        "범위_외",
    ]
    confidence: float  # 의도 분류 신뢰도 (0.0~1.0)

    # ── 2단계 Definition ────────────────────────────────────
    target_files: list[str]  # 수정 대상 JSON 파일 목록 (예: ["Enemies.json"])
    modifications: list[dict]  # 수정 내용 상세
    extracted_ids: dict  # 이름→ID 매핑 (예: {"enemy_id": 1})
    params_sufficient: bool  # 파라미터 충분 여부

    # ── 2.5단계 Operation IR (definition → game_index_resolve → planner) ──
    operation_tuples: list[dict]  # 정규화된 operation IR
    plan_meta: dict  # planner → validator (op_idx → step_ids 역매핑)

    # ── 3단계 Planner ───────────────────────────────────────
    game_context: dict  # 플래너 프롬프트에 주입할 현재 게임 데이터
    # 단계별 실행 명령. 레거시: [{"task": "..."}]. 구조화(3단계): step_id, action_type,
    # target_file, target_info, depends_on, condition, description 등.
    execution_plan: list[dict]

    # ── 4단계 Executor ──────────────────────────────────────
    # 파일명 → 스냅샷 JSON **파일 절대 경로(str)** (내용 dict는 graph/utils/game_state_json 로드)
    current_game_state: dict
    modified_game_state: dict

    # ── 5단계 Validator ─────────────────────────────────────
    validation_results: list  # 파일별 검증 결과 리스트
    validation_summary: str  # 검증 결과 요약 문자열
    validation_details: list[str]  # schema/judge 실패 상세 (synthesizer 가 사용)
    judge_feedback: str  # judge 실패 피드백 텍스트 (synthesizer 가 응답에 첨부)
    success: bool  # 전체 검증 통과 여부
    retry_count: int  # 검증 실패 후 재시도 횟수

    # ── 6단계 Synthesizer ───────────────────────────────────
    final_response: str  # 사용자에게 전달할 최종 응답

    # ── 맵 후보군 (Generation에서 이월) ──────────────────────
    ranked_map_candidates: list[dict]  # 추가: 검색된 맵 후보군 (점수 포함)

    # ── 대화 이력 ────────────────────────────────────────────
    conversation_history: list[dict]  # [{"role": "user"|"assistant", "content": str}]

    # ── 누적 필드 (add reducer — 덮어쓰지 않고 쌓임) ────────
    changes_log: Annotated[list, add]  # 실행 단계별 변경 이력
    tool_results: Annotated[list, add]  # 툴 호출 결과 누적

    # ── 4단계 Executor 추가 필드들 (MVP) ──────────────────────
    backup_paths: Annotated[
        dict, _merge_dict
    ]  # 백업 파일 경로들 {"Skills.json": "/path/to/backup.bak"} — retry 시 첫 실행 경로 보존
    operation_id: str  # 실행 추적용 고유 ID
