"""Feedback text 생성 — schema 실패, judge 실패를 profiler 가 이해할 한국어로 변환."""

from __future__ import annotations

from typing import Any


def build_feedback_text(
    schema_failures: list[dict[str, Any]] | None = None,
    judge_failures: list[dict[str, Any]] | None = None,
) -> str:
    """profiler 재호출 시 주입할 feedback 문자열."""
    lines: list[str] = []

    if schema_failures:
        lines.append("[Schema 검증 실패]")
        for f in schema_failures:
            lines.append(f"  - {f.get('file', '?')}: {f.get('detail', '?')[:200]}")

    if judge_failures:
        lines.append("[의미 검증 실패]")
        for f in judge_failures:
            op = f.get("operation", {})
            reason = f.get("reason", "이유 불명")
            subject = (op.get("subject") or {}).get("name", "?")
            lines.append(f"  - {op.get('file', '?')} '{subject}': {reason}")

    if lines:
        lines.append("\n위 오류를 참고하여 해당 필드를 수정하세요.")

    return "\n".join(lines)
