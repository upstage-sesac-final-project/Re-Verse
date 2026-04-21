"""Validator node — schema 검증 + 룰 기반 soundness 경고 + partial retry.

Phase G 재설계:
- 유저 쿼리와의 비교(`judge_operation` LLM 호출) 제거. 판단 정확도가 낮고
  retry 를 유발해 LLM 낭비. 대신 `soundness_warnings` (룰 기반 경고 리스트)
  를 반환하고 synthesizer 가 포장.
- `success` 는 이제 schema 검증 결과에만 좌우된다.
- `judge_feedback` state 필드는 제거됨 (Task 15).

검증만 수행한다. 사용자 응답 생성은 synthesizer 가 담당.
"""

from __future__ import annotations

import logging

from agent.constants import MAX_RETRY
from agent.editor.nodes.validator.feedback import build_feedback_text
from agent.editor.nodes.validator.retry_loop import run_partial_retry
from agent.editor.nodes.validator.schema_check import validate_changed_files

logger = logging.getLogger(__name__)


def _is_equipment_file(target_file: str) -> bool:
    return target_file in {"Weapons.json", "Armors.json"}


def _iter_event_commands(entry_data: dict | None):
    """changes_log entry 의 data 에서 이벤트 커맨드 list 반복자.

    이벤트 handler 는 data 로 dict 를 반환 (MapEvent / CommonEvent / Troop).
    이 중 list 필드 (pages[].list 또는 list 자체) 를 순회한다.
    """
    if not isinstance(entry_data, dict):
        return
    # CommonEvent: {id, list, ...}
    lst = entry_data.get("list")
    if isinstance(lst, list):
        yield lst
        return
    # MapEvent / Troop: {id, pages: [{list, ...}], ...}
    pages = entry_data.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict) and isinstance(page.get("list"), list):
                yield page["list"]


_ACTOR_STAT_KEYWORDS = (
    "체력",
    "hp",
    "HP",
    "mp",
    "MP",
    "마나",
    "공격력",
    "공격",
    "방어력",
    "방어",
    "민첩",
    "운",
)


def _collect_soundness_warnings(
    changes_log: list[dict],
    operation_tuples: list[dict],
    user_input: str = "",
    execution_plan: list[dict] | None = None,
) -> list[str]:
    """룰 기반 경고 수집.

    룰 카탈로그:
      1. entity_id 누락 — create/update 성공인데 id 추적 안 됨
      2. 전부 skipped — 실행 계획 있었는데 아무것도 안 함
      3. 무기/방어구 price=0 create — 가격 책정 빠짐 경고
      4. 무기/방어구 params 전부 0 create — 능력치 빠짐 경고
      5. 이벤트 code=0 종결 — 마지막 커맨드가 terminator (code=0) 가 아님
      6. HP 값 이상 — 적/액터 params[0]=0 create 는 전투 불가
      7. (Task 31) Actor create + user 가 스탯 수치 지정 — Actor 스키마에 params 없음.
         스탯은 Classes.params 곡선으로 관리되므로 사용자 안내.
    """
    warnings: list[str] = []
    user_has_stat_spec = bool(user_input) and any(kw in user_input for kw in _ACTOR_STAT_KEYWORDS)

    for entry in changes_log:
        if not entry.get("success"):
            continue
        if entry.get("skipped"):
            continue
        action = (entry.get("action") or "").lower()
        tf = entry.get("target_file", "?")

        # 룰 1: entity_id 누락
        if action in ("create", "update", "update_actor") and entry.get("entity_id") is None:
            warnings.append(
                f"{tf} {action}: entity_id 가 비어 있습니다 — 실행은 보고됐으나 id 추적이 안 됩니다."
            )

        # 룰 3/4: 장비 create 의 price / params 체크
        data = entry.get("data")
        if action.startswith("create") and _is_equipment_file(tf) and isinstance(data, dict):
            price = data.get("price")
            if isinstance(price, int) and price == 0:
                warnings.append(
                    f"{tf}: '{data.get('name', '?')}' 가격이 0 입니다 — 의도적 free item 이 아니면 확인 필요"
                )
            params = data.get("params")
            if isinstance(params, list) and len(params) == 8 and all(p == 0 for p in params):
                warnings.append(
                    f"{tf}: '{data.get('name', '?')}' 능력치(params)가 전부 0 입니다 — 장비 효과 없음"
                )

        # 룰 6: Enemies/Actors params[0] (MHP) 체크
        if (
            action.startswith("create")
            and tf in {"Enemies.json", "Actors.json"}
            and isinstance(data, dict)
        ):
            params = data.get("params")
            if isinstance(params, list) and params and params[0] == 0:
                warnings.append(
                    f"{tf}: '{data.get('name', '?')}' 최대 HP 가 0 입니다 — 전투 불가 상태"
                )

        # 룰 7 (Task 31): Actor create 인데 user 가 체력/MP/공격력 등 스탯 수치를
        # 지정한 경우. Actor 스키마에는 params 가 없고 Classes.params (레벨 곡선)
        # 가 실제 스탯을 결정하므로 반영 안 됨. 안내 필요.
        if (
            action.startswith("create")
            and tf == "Actors.json"
            and user_has_stat_spec
            and isinstance(data, dict)
        ):
            name = data.get("name", "?")
            warnings.append(
                f"Actors.json: '{name}' 생성 시 지정한 스탯(체력/MP/공격력 등)은 "
                f"Actor 자체에 저장되지 않습니다. Classes 레벨 곡선으로 관리되므로 "
                f"해당 직업(Class) 수정 또는 신규 Class 생성이 필요합니다."
            )

        # 룰 8 (Task 29): Actor create 인데 profiler 가 "_class_not_found" 힌트를
        # 남긴 경우. execution_plan.step.target_info 에 접근 (changes_log.data 는
        # pydantic 통과 후라 _ 접두사 힌트가 날아감).
        if action.startswith("create") and tf == "Actors.json" and execution_plan:
            sid = entry.get("step_id")
            matching = next(
                (
                    s
                    for s in execution_plan
                    if s.get("step_id") == sid and s.get("target_file") == "Actors.json"
                ),
                None,
            )
            if matching:
                ti = matching.get("target_info") or {}
                missing_class = ti.get("_class_not_found")
                if missing_class:
                    name = (data.get("name") if isinstance(data, dict) else None) or ti.get(
                        "name", "?"
                    )
                    warnings.append(
                        f"Actors.json: '{name}' 의 직업 '{missing_class}' 가 Classes.json 에 "
                        f"없어 기본 classId 가 세팅됐습니다. 해당 직업을 먼저 생성하거나 "
                        f"기존 직업명을 지정하세요."
                    )

        # 룰 5: 이벤트 list code=0 종결 검증
        if (
            "event" in action
            or tf in {"CommonEvents.json", "Troops.json"}
            or (tf.startswith("Map") and tf.endswith(".json"))
        ):
            for cmd_list in _iter_event_commands(data):
                if not cmd_list:
                    continue
                last = cmd_list[-1]
                if not (isinstance(last, dict) and last.get("code") == 0):
                    warnings.append(
                        f"{tf}: 이벤트 커맨드 list 가 code=0 으로 종결되지 않았습니다 — "
                        f"RPG Maker 런타임 오류 위험"
                    )
                    break

    # 룰 2: execution_plan 은 있었는데 changes_log 가 전부 skipped 면 아무것도 안 한 상태
    if operation_tuples and changes_log and all(e.get("skipped") for e in changes_log):
        warnings.append("실행 계획이 있었지만 전부 skip 되었습니다 — 의도와 다를 수 있습니다.")

    return warnings


async def validator(state: dict) -> dict:
    """Validator node entry point."""
    import time

    _t0 = time.perf_counter()
    logger.info("─── Validator START ────────────────────────────────")

    changes_log: list[dict] = state.get("changes_log", [])
    execution_plan: list[dict] = state.get("execution_plan", [])
    operation_tuples: list[dict] = state.get("operation_tuples", [])
    game_id: str = state.get("game_id", "")
    retry_count: int = state.get("retry_count", 0)
    # Phase G: user_input / resolved_input / plan_meta 는 judge_operation 에만
    # 쓰던 변수. judge 제거와 함께 이 함수에서는 더 이상 참조 안 함.

    logger.info(
        "[Validator] entries=%d retry=%d ops=%d",
        len(changes_log),
        retry_count,
        len(operation_tuples),
    )

    # 1. 실행 중 실패가 있었는지 확인
    exec_failures = [e for e in changes_log if not e.get("success")]
    if exec_failures:
        if retry_count < MAX_RETRY:
            retried = await run_partial_retry(
                exec_failures,
                execution_plan,
                game_id,
                retry_count,
                previous_changes_log=changes_log,
            )
            if retried.get("success"):
                changes_log = retried["changes_log"]
            else:
                elapsed = time.perf_counter() - _t0
                logger.info(
                    "─── Validator END (elapsed=%.2fs, result=FAIL, reason=exec_retry_failed) ──",
                    elapsed,
                )
                return {
                    "success": False,
                    "retry_count": retry_count + 1,
                    "validation_summary": retried.get("summary", "실행 실패"),
                }

    # 2. Schema 검증
    modified_files = sorted(
        set(
            f
            for entry in changes_log
            for f in entry.get("modified_files", [])
            if entry.get("success")
        )
    )
    schema_results = validate_changed_files(game_id, modified_files)
    schema_failures = [r for r in schema_results if not r["valid"]]

    if schema_failures and retry_count < MAX_RETRY:
        feedback = build_feedback_text(schema_failures=schema_failures)
        retried = await run_partial_retry(
            schema_failures,
            execution_plan,
            game_id,
            retry_count,
            feedback_text=feedback,
            previous_changes_log=changes_log,
        )
        if retried.get("success"):
            schema_results = validate_changed_files(game_id, modified_files)
            schema_failures = [r for r in schema_results if not r["valid"]]

    if schema_failures:
        summary = f"Schema 검증 실패: {len(schema_failures)} 파일"
        elapsed = time.perf_counter() - _t0
        logger.info(
            "─── Validator END (elapsed=%.2fs, result=FAIL, reason=schema) ─────",
            elapsed,
        )
        return {
            "success": False,
            "retry_count": retry_count + 1,
            "validation_summary": summary,
            "validation_details": [f["detail"] for f in schema_failures],
        }

    # 3. Phase G: judge_operation LLM 호출 제거. 대신 룰 기반 soundness 경고.
    soundness_warnings = _collect_soundness_warnings(
        changes_log,
        operation_tuples,
        user_input=state.get("user_input", "") or "",
        execution_plan=execution_plan,
    )
    if soundness_warnings:
        logger.info(
            "[Validator] soundness_warnings %d건 — synthesizer 가 포장", len(soundness_warnings)
        )

    # 4. 최종 판정 — schema 만 성공 기준. 경고는 차단 아님.
    success = len(schema_failures) == 0
    summary = "성공" if not soundness_warnings else f"성공 (참고사항 {len(soundness_warnings)}건)"

    elapsed = time.perf_counter() - _t0
    logger.info(
        "─── Validator END (elapsed=%.2fs, result=%s, schema_fail=%d, warnings=%d) ──",
        elapsed,
        "OK" if success else "FAIL",
        len(schema_failures),
        len(soundness_warnings),
    )
    return {
        "success": success,
        "retry_count": retry_count + (0 if success else 1),
        "validation_summary": summary,
        "soundness_warnings": soundness_warnings,
    }
