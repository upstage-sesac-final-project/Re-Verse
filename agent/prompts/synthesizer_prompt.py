"""Synthesizer 프롬프트 — 실행 결과를 사용자 친화적 응답으로 변환."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState

_SYSTEM = """\
당신은 RPG Maker 게임 제작 AI 어시스턴트 'Re:Verse'입니다.
게임 요소 생성·수정·조회 작업이 완료된 후, 그 결과를 사용자에게 친절하고 명확하게 설명하세요.

## 응답 원칙

1. 무엇이 변경/생성/조회되었는지 구체적으로 설명한다.
2. 수치 변경은 "이전값 → 이후값" 형태로 표시한다.
3. 생성된 요소는 주요 속성(이름, HP, 공격력 등)을 간략히 소개한다.
4. 조회 결과는 핵심 정보만 읽기 쉽게 정리한다.
5. 실패 시에는 원인을 설명하고 다음에 어떻게 하면 되는지 안내한다.
6. 3~5문장 이내로 간결하게 작성한다. 불필요한 사족은 붙이지 않는다.
7. 반말·존댓말 구분 없이 친근하지만 명확한 어투를 사용한다.

## Markdown 형식 규칙

응답은 반드시 Markdown으로 작성한다. 프론트엔드에서 그대로 렌더링된다.

- 요소 이름·파일명은 **굵게** 표시한다.
- 수치 나열이 2개 이상이면 `-` 목록으로 정리한다.
- 수치 변경은 `100 → 200` 형태로 인라인 코드로 표시한다.
- 헤더(#)는 사용하지 않는다. 본문만 작성한다.

## 성공 응답 예시

수정:
**슬라임**의 HP를 `100 → 200`으로 올렸습니다. 전투가 좀 더 어려워지겠네요!

생성:
**파이어볼** 스킬을 만들었습니다.
- MP 소비: `30`
- 데미지: `150` (불 속성, 적 전체)

조회:
현재 등록된 적은 총 3종입니다.
- **슬라임** — HP `100`
- **고블린** — HP `150`
- **드래곤** — HP `9999`

## 실패 응답 예시

**슬라임킹**을 찾지 못했습니다. 이름이 정확한지 확인해주세요.
`적 목록 보여줘`로 등록된 적을 확인할 수 있어요.\
"""

_MAX_ITEMS = 5
_MAX_FIELDS = 6
_MAX_LOGS = 8
_MAX_ERRORS = 5
_TEXT_LIMIT = 120


def _short_text(value: Any, limit: int = _TEXT_LIMIT) -> str:
    text = str(value).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _join_limited(values: list[str], limit: int = _MAX_ITEMS) -> str:
    sample = values[:limit]
    if not sample:
        return ""
    if len(values) <= limit:
        return ", ".join(sample)
    return f"{', '.join(sample)} 외 {len(values) - limit}개"


def _entity_label(item: dict[str, Any]) -> str | None:
    name = item.get("name") or item.get("displayName") or item.get("nickname")
    if isinstance(name, str) and name.strip():
        item_id = item.get("id")
        if isinstance(item_id, int):
            return f"{name}(id={item_id})"
        return name

    item_id = item.get("id")
    if isinstance(item_id, int):
        return f"id={item_id}"
    return None


def _collect_labels(items: list[Any]) -> list[str]:
    labels: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = _entity_label(item)
        if label and label not in labels:
            labels.append(label)
    return labels


def _index_entries(items: list[Any]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, int):
            indexed[item_id] = item
    return indexed


def _format_id_labels(indexed: dict[int, dict[str, Any]], ids: list[int]) -> str:
    labels: list[str] = []
    for item_id in ids[:_MAX_ITEMS]:
        item = indexed.get(item_id)
        label = _entity_label(item) if item else None
        labels.append(label or f"id={item_id}")
    if len(ids) <= _MAX_ITEMS:
        return ", ".join(labels)
    return f"{', '.join(labels)} 외 {len(ids) - _MAX_ITEMS}개"


def _dict_metadata(value: dict[str, Any]) -> list[str]:
    meta: list[str] = []

    display_name = value.get("displayName")
    if isinstance(display_name, str) and display_name.strip():
        meta.append(f"displayName={display_name}")

    name = value.get("name")
    if isinstance(name, str) and name.strip():
        meta.append(f"name={name}")

    width = value.get("width")
    height = value.get("height")
    if isinstance(width, int) and isinstance(height, int):
        meta.append(f"맵 크기 {width}x{height}")

    events = value.get("events")
    if isinstance(events, list):
        event_count = sum(1 for event in events if event)
        meta.append(f"이벤트 {event_count}개")

    party_members = value.get("partyMembers")
    if isinstance(party_members, list):
        meta.append(f"partyMembers {len(party_members)}명")

    return meta


def _summarize_snapshot(file_name: str, value: Any) -> str:
    if isinstance(value, list):
        entries = [item for item in value if item is not None]
        line = f"{file_name}: 항목 {len(entries)}개"
        labels = _collect_labels(entries)
        if labels:
            line += f". 대표 항목: {_join_limited(labels)}"
        return line

    if isinstance(value, dict):
        line = f"{file_name}: 객체 키 {len(value)}개"
        meta = _dict_metadata(value)
        if meta:
            line += f". {_join_limited(meta, _MAX_FIELDS)}"
        return line

    return f"{file_name}: {_short_text(value)}"


def _summarize_list_diff(file_name: str, before: list[Any], after: list[Any]) -> str:
    before_entries = [item for item in before if item is not None]
    after_entries = [item for item in after if item is not None]

    fragments = [f"{file_name}: 항목 {len(before_entries)} → {len(after_entries)}개"]
    before_by_id = _index_entries(before_entries)
    after_by_id = _index_entries(after_entries)

    if before_by_id and after_by_id:
        added_ids = sorted(after_by_id.keys() - before_by_id.keys())
        removed_ids = sorted(before_by_id.keys() - after_by_id.keys())
        changed_ids = sorted(
            item_id
            for item_id in before_by_id.keys() & after_by_id.keys()
            if before_by_id[item_id] != after_by_id[item_id]
        )

        if added_ids:
            fragments.append(f"추가: {_format_id_labels(after_by_id, added_ids)}")
        if changed_ids:
            fragments.append(f"변경: {_format_id_labels(after_by_id, changed_ids)}")
        if removed_ids:
            fragments.append(f"삭제: {_format_id_labels(before_by_id, removed_ids)}")

    if len(fragments) == 1:
        labels = _collect_labels(after_entries)
        if labels:
            fragments.append(f"대표 항목: {_join_limited(labels)}")
        elif before != after:
            fragments.append("세부 필드 변경 있음")

    return ". ".join(fragments)


def _summarize_dict_diff(file_name: str, before: dict[str, Any], after: dict[str, Any]) -> str:
    changed_keys = [
        key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)
    ]
    fragments = [f"{file_name}: 변경된 상위 키 {len(changed_keys)}개"]
    if changed_keys:
        fragments.append(f"키: {_join_limited(changed_keys, _MAX_FIELDS)}")

    meta = _dict_metadata(after)
    if meta:
        fragments.append(_join_limited(meta, _MAX_FIELDS))

    return ". ".join(fragments)


def _summarize_snapshot_changes(current: dict[str, Any], modified: dict[str, Any]) -> str:
    lines: list[str] = []
    for file_name in sorted(modified):
        before = current.get(file_name)
        after = modified[file_name]

        if before == after:
            continue

        if isinstance(before, list) and isinstance(after, list):
            lines.append(f"- {_summarize_list_diff(file_name, before, after)}")
            continue

        if isinstance(before, dict) and isinstance(after, dict):
            lines.append(f"- {_summarize_dict_diff(file_name, before, after)}")
            continue

        lines.append(f"- {_summarize_snapshot(file_name, after)}")

    return "\n".join(lines)


def _summarize_snapshot_state(snapshot: dict[str, Any]) -> str:
    lines = [
        f"- {_summarize_snapshot(file_name, value)}"
        for file_name, value in sorted(snapshot.items())
    ]
    return "\n".join(lines)


def _format_errors(validation_results: list[Any]) -> str:
    flattened: list[Any] = []
    for result in validation_results:
        if isinstance(result, dict):
            flattened.extend(result.get("errors", []))

    lines: list[str] = []
    for error in flattened[:_MAX_ERRORS]:
        if not isinstance(error, dict):
            lines.append(f"- {_short_text(error)}")
            continue

        loc = error.get("loc", "$")
        msg = error.get("msg") or error.get("message") or "알 수 없는 오류"
        parts = [f"{loc}: {msg}"]

        expected = error.get("expected")
        if expected is not None:
            parts.append(f"expected={_short_text(expected, 60)}")

        input_value = error.get("input")
        raw_value = error.get("raw")
        sample_value = input_value if input_value is not None else raw_value
        if sample_value is not None and not isinstance(sample_value, (dict, list)):
            parts.append(f"input={_short_text(sample_value, 60)}")

        lines.append("- " + " | ".join(parts))

    if len(flattened) > _MAX_ERRORS:
        lines.append(f"- 외 {len(flattened) - _MAX_ERRORS}개 오류")

    return "\n".join(lines)


def _format_changes_log(changes: list[Any]) -> str:
    lines: list[str] = []
    for entry in changes[:_MAX_LOGS]:
        if not isinstance(entry, dict):
            lines.append(f"- {_short_text(entry)}")
            continue

        step = entry.get("step_id", entry.get("step", "?"))
        tool_name = entry.get("tool_name", "unknown")
        status = "성공" if entry.get("success", False) else "실패"
        detail = (
            entry.get("stdout")
            or entry.get("message")
            or entry.get("skip_reason")
            or entry.get("stderr")
            or entry.get("error")
            or entry.get("user_input")
            or ""
        )
        if not detail:
            fallback_parts: list[str] = []
            for key in ("target_file", "file", "name", "action", "field"):
                value = entry.get(key)
                if value:
                    fallback_parts.append(f"{key}={value}")
            detail = ", ".join(fallback_parts)
        line = f"- step {step} {tool_name}: {status}"
        if detail:
            line += f" | {_short_text(detail)}"
        lines.append(line)

    if len(changes) > _MAX_LOGS:
        lines.append(f"- 외 {len(changes) - _MAX_LOGS}개 step")

    return "\n".join(lines)


def build_prompt(state: AgentState) -> list[BaseMessage]:
    intent = state.get("intent", "")
    user_input = state.get("user_input", "")
    passed = state.get("success", True)
    validation_results = state.get("validation_results") or []
    validation_summary = state.get("validation_summary") or ""
    current = state.get("current_game_state") or {}
    modified = state.get("modified_game_state") or {}
    changes = state.get("changes_log") or []

    # ── 결과 요약 섹션 구성 ───────────────────────────────
    sections: list[str] = [
        f"## 사용자 원본 요청\n{user_input}",
        f"## 의도\n{intent}",
        f"## 실행 결과\n{'성공' if passed else '실패'}",
    ]

    if validation_summary:
        sections.append(f"## 검증 요약\n{validation_summary}")

    formatted_errors = _format_errors(validation_results)
    if formatted_errors:
        sections.append("## 오류 내용\n" + formatted_errors)

    if changes:
        sections.append("## 변경 이력\n" + _format_changes_log(changes))

    if current and modified:
        snapshot_summary = _summarize_snapshot_changes(current, modified)
        if snapshot_summary:
            sections.append("## 데이터 요약\n" + snapshot_summary)
    elif modified:
        sections.append("## 데이터 요약\n" + _summarize_snapshot_state(modified))
    elif current:
        sections.append("## 데이터 요약\n" + _summarize_snapshot_state(current))

    human_content = "\n\n".join(sections)

    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=human_content),
    ]
