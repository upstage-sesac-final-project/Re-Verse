"""Responder — final_response 생성 (synthesizer 흡수).

성공: 결정론 템플릿, LLM 0회.
실패: 결정론 템플릿 + feedback.
"""

from __future__ import annotations

from typing import Any


def build_final_response(
    success: bool,
    summary: str,
    changes_log: list[dict[str, Any]],
    details: list[str] | None = None,
    soundness_warnings: list[str] | None = None,
) -> str:
    """최종 사용자 응답 문자열 생성.

    Phase H: soundness_warnings 포장 추가. YB.md 8-5 의 "성공 + 경고 통합" 경로를
    결정론 템플릿으로 처리 (LLM 0회). 경고가 다중이면 bullet list 로 렌더.
    """
    if success:
        resp = _success_response(changes_log)
        if soundness_warnings:
            resp += "\n\n" + _render_soundness_warnings(soundness_warnings)
        return resp
    return _failure_response(summary, changes_log, details)


def _render_soundness_warnings(warnings: list[str]) -> str:
    """soundness_warnings 리스트를 사용자 친화적 bullet 로 포장."""
    if len(warnings) == 1:
        return f"⚠️ 참고: {warnings[0]}"
    header = f"⚠️ 참고 ({len(warnings)}건):"
    lines = [f"  - {w}" for w in warnings]
    return "\n".join([header, *lines])


def build_hold_response(hold_question: str, hold_reason: str | None = None) -> str:
    """Hold 응답 렌더 — definition 이 resolve=False 로 끝낼 때 synthesizer 가 호출.

    현 구현은 hold_question 을 그대로 돌려준다. 추후 reason 별 템플릿 세분화 예정.
    """
    return hold_question or "추가 정보가 필요합니다. 구체적으로 알려주시겠어요?"


def _format_query_result(target: str, data: Any) -> str:
    """조회 결과를 사용자 친화적 문자열로 변환."""
    if data is None:
        return f"  - {target}: 조회 결과 없음"

    # 단건 dict
    if isinstance(data, dict):
        name = data.get("name", "")
        eid = data.get("id")
        if name:
            label = f"'{name}'" + (f" (id={eid})" if eid is not None else "")
            return f"  - {target}: {label} 이(가) 존재합니다."
        return f"  - {target}: id={eid} 조회 완료"

    # 리스트
    if isinstance(data, list):
        if not data:
            return f"  - {target}: 해당하는 항목이 없습니다."
        names = [str(e.get("name", f"id={e.get('id', '?')}")) for e in data if isinstance(e, dict)]
        if len(names) <= 10:
            listing = ", ".join(names)
        else:
            listing = ", ".join(names[:10]) + f" 외 {len(names) - 10}건"
        return f"  - {target}: 총 {len(names)}건 — {listing}"

    return f"  - {target}: 조회 완료"


def _success_response(changes_log: list[dict]) -> str:
    lines = ["요청을 성공적으로 처리했습니다."]

    for entry in changes_log:
        if not entry.get("success"):
            continue
        action = entry.get("action", "")
        target = entry.get("target_file", "")
        data = entry.get("data")

        name = ""
        if isinstance(data, dict):
            name = data.get("name", "")

        entity_id = entry.get("entity_id")

        if action == "create":
            lines.append(f"  - {target}: '{name}' 생성 (id={entity_id})")
        elif action in ("update", "update_actor"):
            lines.append(f"  - {target}: '{name or f'id={entity_id}'}' 수정")
        elif action == "delete":
            lines.append(f"  - {target}: id={entity_id} 삭제")
        elif action == "append_system_type":
            if isinstance(data, dict):
                lines.append(
                    f"  - System.json: {data.get('system_key')}에 '{data.get('value')}' 추가"
                )
        elif action in ("get", "search", "list"):
            lines.append(_format_query_result(target, data))
        else:
            lines.append(f"  - {target}: {action}")

    return "\n".join(lines)


def _failure_response(
    summary: str,
    changes_log: list[dict],
    details: list[str] | None,
) -> str:
    # 전체가 UNSUPPORTED인 경우 간결한 안내 메시지
    fail = [e for e in changes_log if not e.get("success")]
    all_unsupported = fail and all(
        "UNSUPPORTED" in str(e.get("tool_name", "")) or "UNSUPPORTED" in str(e.get("error", ""))
        for e in fail
    )
    if all_unsupported:
        return (
            "현재 지원하지 않는 기능입니다. 다른 방식으로 요청하시거나, 버그 리포트에 작성해주세요."
        )

    lines = [f"요청 처리 중 문제가 발생했습니다: {summary}"]

    # 부분 성공 알림
    ok = [e for e in changes_log if e.get("success")]
    if ok:
        lines.append(f"\n부분 성공 ({len(ok)} 건):")
        for entry in ok:
            lines.append(f"  - {entry.get('target_file', '?')}: {entry.get('action', '?')}")

    # 실패 상세
    if details:
        lines.append("\n실패 상세:")
        for d in details:
            lines.append(f"  - {d}")

    if fail:
        lines.append(f"\n실행 실패 ({len(fail)} 건):")
        for entry in fail:
            lines.append(f"  - {entry.get('target_file', '?')}: {entry.get('error', '?')}")

    return "\n".join(lines)
