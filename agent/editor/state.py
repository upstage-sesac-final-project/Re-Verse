"""AgentState — LangGraph 워크플로우의 공유 상태."""

from operator import add
from typing import Annotated, Any, Literal, TypedDict


def get_latest_per_step(changes_log: list[dict]) -> list[dict]:
    """changes_log 에서 step_id 기준 가장 최신(뒤쪽) 엔트리만 추린다.

    `changes_log` 는 Annotated[list, add] reducer 라 retry 시 이전 로그가 누적된다.
    validator/judge 가 "같은 step 에 대한 최신 결과" 만 봐야 할 때 이 헬퍼를 사용한다.
    step_id 가 없는 엔트리는 그대로 유지(순서 보존).
    """
    latest_by_sid: dict[Any, dict] = {}
    no_sid: list[dict] = []
    for entry in changes_log:
        sid = entry.get("step_id") if isinstance(entry, dict) else None
        if sid is None:
            no_sid.append(entry)
        else:
            latest_by_sid[sid] = entry
    return no_sid + list(latest_by_sid.values())


def _merge_dict(left: dict, right: dict) -> dict:
    """dict 병합 reducer. right가 비어 있으면 left를 그대로 유지한다."""
    if not right:
        return left
    return {**left, **right}


class AgentState(TypedDict, total=False):
    # ── 입력 ────────────────────────────────────────────────
    user_input: str  # 사용자 원본 입력 (따옴표·특수문자 포함 원문 그대로 보존)
    resolved_input: (
        str  # router 가 coref 해소한 입력 (없으면 빈 문자열). 원본은 user_input 에 남긴다
    )
    game_id: str  # 수정 대상 게임 ID (예: "game_001")
    conversation_id: str  # pending_store 조회 키 (세션 단위)

    # ── 1단계 Router ────────────────────────────────────────
    # Phase C 부터 영문 IntentValue (agent/editor/intents.py) 사용.
    intent: Literal[
        "object_create",
        "object_update",
        "event_create",
        "event_update",
        "query",
        "game_overview",
        "multi_intent",
        "out_of_scope",
        "small_talk",
        "clarification_needed",
    ]
    confidence: float  # 의도 분류 신뢰도 (0.0~1.0)
    # parsed_command = { field, target, action, property, value, bulk_scope } — definition / reader 가 소비
    # property/value/bulk_scope 는 Phase D+E+F 후속 sprint (parsed_command 확장) 에서 추가
    parsed_command: dict
    # 다중 엔티티 입력("슬라임이랑 드래곤 만들어줘") 일 때 primary 외 추가 대상.
    # 1 개만이면 빈 list. 각 엔트리: {field, target, action, property, value}
    parsed_extractions: list[dict]
    needs_context_lookup: bool  # 조사·대명사 참조 여부
    pending_resumed: bool  # 이번 턴이 이전 hold 의 응답인지

    # ── 2단계 Definition ────────────────────────────────────
    target_files: list[str]  # 수정 대상 JSON 파일 목록 (예: ["Enemies.json"])
    modifications: list[dict]  # 수정 내용 상세
    extracted_ids: dict  # 이름→ID 매핑 (예: {"enemy_id": 1})
    params_sufficient: bool  # 파라미터 충분 여부
    # Phase D 에서 실사용 시작. hold / resolve 경로.
    resolve: bool  # 기본 True. hold 활성 시 False
    field: str  # 카테고리 (액터 / 무기 / 이벤트 ...)
    target: str  # 확정된 이름·id 요약
    description: str  # 한줄 요약 (profiler 가 LLM 프롬프트에 활용)
    reference_checks: list[dict]  # [{category, name, status(있음/없음/애매), candidates?}]
    hold_reason: Literal[
        "already_exists",
        "not_found",
        "ambiguous_ref",
        "page_condition_unclear",
        "ambiguous_position",
        "destination_unclear",  # teleport 목적지 좌표 미지정 (이벤트 위치와 구분)
    ]
    hold_question: str  # 유저에게 되묻는 문장
    message_for_user: str  # definition 이 params 불충분 시 유저용 메시지 (drift 정리)
    # router 가 pending resume 시 definition 이 소비. snapshot 에 이전 턴의 field/target/... 보존
    resumed_snapshot: dict

    # ── 2.5단계 Operation IR (definition → operation_ir.resolve → planner) ──
    operation_tuples: list[dict]  # 정규화된 operation IR
    plan_meta: dict  # planner → validator (op_idx → step_ids 역매핑)

    # ── 3단계 Planner ───────────────────────────────────────
    # 단계별 실행 명령. 레거시: [{"task": "..."}]. 구조화(3단계): step_id, action_type,
    # target_file, target_info, depends_on, condition, description 등.
    execution_plan: list[dict]
    # Phase E 에서 실사용 시작. profiler 가 채울 빈칸 명세.
    fill_slots: list[dict]  # [{step_id, field_name, hint, type?}]

    # ── 3.5단계 Profiler ────────────────────────────────────
    filled_values: dict  # {step_id: {field_name: value}} — profiler 가 LLM 으로 채운 결과

    # ── 4단계 Executor ──────────────────────────────────────
    # 파일명 → 스냅샷 JSON **파일 절대 경로(str)** (내용 dict는 graph/utils/game_state_json 로드)
    current_game_state: dict
    modified_game_state: dict
    modified_file_paths: list[str]  # 실제 수정된 data/*.json 절대 경로 (drift 정리)

    # ── 5단계 Validator ─────────────────────────────────────
    validation_results: list  # 파일별 검증 결과 리스트
    validation_summary: str  # 검증 결과 요약 문자열
    validation_details: list[str]  # schema 실패 상세 (synthesizer 가 사용)
    success: bool  # 전체 검증 통과 여부
    retry_count: int  # 검증 실패 후 재시도 횟수
    soundness_warnings: list[str]  # 룰 기반 경고 (차단 아님, synthesizer 가 포장)

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
