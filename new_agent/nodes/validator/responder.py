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
) -> str:
    """최종 사용자 응답 문자열 생성."""
    if success:
        return _success_response(changes_log)
    return _failure_response(summary, changes_log, details)


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
                lines.append(f"  - System.json: {data.get('system_key')}에 '{data.get('value')}' 추가")
        elif action in ("get", "search", "list"):
            count = len(data) if isinstance(data, list) else 1
            lines.append(f"  - {target}: {count}건 조회")
        else:
            lines.append(f"  - {target}: {action}")

    return "\n".join(lines)


def _failure_response(
    summary: str,
    changes_log: list[dict],
    details: list[str] | None,
) -> str:
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

    fail = [e for e in changes_log if not e.get("success")]
    if fail:
        lines.append(f"\n실행 실패 ({len(fail)} 건):")
        for entry in fail:
            lines.append(f"  - {entry.get('target_file', '?')}: {entry.get('error', '?')}")

    return "\n".join(lines)
