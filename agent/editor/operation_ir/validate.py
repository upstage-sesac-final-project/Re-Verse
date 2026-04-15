"""Operation IR degenerate 검증.

definition Step 10 에서 호출해, update/delete/read 인데
(a) subject 미식별 또는 (b) updates 페이로드 비어있음 을 감지한다.
감지 시 사용자용 안내 메시지와 함께 (False, message) 반환.
"""

from __future__ import annotations


def validate_operation_tuples(ops: list[dict], extractions: list[dict]) -> tuple[bool, str]:
    """update/delete/read op의 degenerate 패턴 감지.

    degenerate 판정 기준 (아래 중 하나 이상):
      (a) action이 update/delete/read인데 subject에 id/name 모두 없음 (대상 미식별)
      (b) action에 'update' 포함인데 updates 페이로드가 어디에도 비어있음

    예: `독 상태이상의 지속 턴을 5로` → Step 4 매칭 실패로 subject.name=None →
    (a) 적중. Executor에서 `update_all({})` silent no-op로 통과하는 패턴 차단.

    Returns:
        (True, "") — 정상
        (False, message) — degenerate. message는 사용자 안내용
    """
    for op in ops:
        action = (op.get("op") or op.get("action") or "").lower()
        if not any(kw in action for kw in ("update", "delete", "read")):
            continue

        subject = op.get("subject") if isinstance(op.get("subject"), dict) else {}
        sid = subject.get("id")
        sname = subject.get("name")
        # subject.name이 literal 'None' 문자열로 들어오는 케이스도 취급
        if isinstance(sname, str) and sname.strip().lower() in ("", "none"):
            sname = None

        subject_missing = sid in (None, "", "NEW") and not sname

        # updates 페이로드 탐색 (update 계열만)
        updates_empty = False
        if "update" in action:
            # Step 5 경로: op["field"] + op["value"] 직접 구조
            if op.get("field") and op.get("value") is not None:
                updates_empty = False
            else:
                # Step 6 LLM 경로: target_info.updates / value.raw_updates
                ti = op.get("target_info") or {}
                updates = ti.get("updates") if isinstance(ti, dict) else None
                if not updates:
                    val = op.get("value") or {}
                    if isinstance(val, dict):
                        updates = val.get("raw_updates")
                updates_empty = not isinstance(updates, dict) or len(updates) == 0

        if not subject_missing and not updates_empty:
            continue

        # 안내 메시지 작성
        hinted_name = sname or ""
        if not hinted_name:
            for ext in extractions:
                ext_action = (ext.get("action") or "").upper()
                if ext_action in ("UPDATE", "DELETE", "READ") and ext.get("subject"):
                    hinted_name = ext["subject"]
                    break

        target_file = op.get("file") or "?"
        if subject_missing and hinted_name:
            msg = (
                f"'{hinted_name}'을(를) {target_file}에서 찾지 못했습니다. "
                "정확한 이름이나 ID를 알려주세요."
            )
        elif subject_missing:
            msg = (
                f"{target_file}에서 수정할 대상을 특정하지 못했습니다. "
                "어떤 항목을 바꾸고 싶은지 구체적으로 알려주세요."
            )
        elif hinted_name:
            msg = (
                f"'{hinted_name}'에서 변경할 필드가 명확하지 않습니다. "
                "어떤 값을 어떻게 바꿀지 알려주세요."
            )
        else:
            msg = (
                f"{target_file}에서 변경할 필드가 명확하지 않습니다. "
                "어떤 값을 바꾸고 싶은지 알려주세요."
            )
        return False, msg

    return True, ""
