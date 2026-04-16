"""Synthesizer 프롬프트 — 실행 결과를 사용자 친화적 응답으로 변환."""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.editor.state import AgentState
from agent.editor.utils.game_state_json import load_snapshot_payload

_SYSTEM = """\
당신은 RPG Maker 게임 제작 AI 어시스턴트 'Re:Verse'입니다.
게임 요소 생성·수정·조회 작업이 완료된 후, 그 결과를 사용자에게 친절하고 명확하게 설명하세요.

## 응답 원칙

1. 무엇이 변경/생성/조회되었는지 구체적으로 설명한다.
2. **수정 전 게임 데이터**와 **수정 후 게임 데이터**를 비교해 실제로 바뀐 필드만 "이전값 → 이후값" 형태로 표시한다.
3. 생성된 요소는 주요 속성(이름, HP, 공격력 등)을 간략히 소개한다.
4. 조회 결과는 핵심 정보만 읽기 쉽게 정리한다.
5. 실패 시에는 원인을 설명하고 다음에 어떻게 하면 되는지 안내한다.
6. 3~5문장 이내로 간결하게 작성한다. 불필요한 사족은 붙이지 않는다.
7. 반말·존댓말 구분 없이 친근하지만 명확한 어투를 사용한다.

## 정확한 변경 사항 보고 원칙

- **실제 변경 사항** 섹션이 있으면 그것을 우선해서 "필드명: 이전값 → 이후값" 형태로 보고한다.
- 변경 이력(`changes_log`)이나 수정 데이터만 있을 때는 **추측하지 말고** "설정이 업데이트되었습니다" 같은 일반적 표현을 쓴다.
- **필드 의미를 임의로 해석하지 말고**, 스키마 설명이 있으면 그것을 참고한다.

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


def _extract_actual_changes_from_snapshots(
    current_snapshot: dict, modified_snapshot: dict
) -> list[str]:
    """전후 스냅샷을 비교해 실제 변경된 내용을 문장으로 요약한다."""
    summaries = []

    for filename, modified_data in modified_snapshot.items():
        current_data = current_snapshot.get(filename, {})

        # 단일 객체(System.json 등)
        if isinstance(modified_data, dict) and not isinstance(modified_data, list):
            if isinstance(current_data, dict):
                for field, new_val in modified_data.items():
                    old_val = current_data.get(field)
                    if old_val != new_val:
                        summaries.append(f"{filename}의 {field}: `{old_val}` → `{new_val}`")
            continue

        # 배열 형태 (Actors.json, Items.json 등)
        if isinstance(modified_data, list) and isinstance(current_data, list):
            for idx, modified_item in enumerate(modified_data):
                if not isinstance(modified_item, dict) or idx >= len(current_data):
                    continue
                current_item = current_data[idx]
                if not isinstance(current_item, dict):
                    continue

                item_name = modified_item.get("name", f"ID {modified_item.get('id', idx)}")
                for field, new_val in modified_item.items():
                    old_val = current_item.get(field)
                    if old_val != new_val:
                        summaries.append(f"{item_name}의 {field}: `{old_val}` → `{new_val}`")

    return summaries


def _extract_actual_changes(current_snapshot: dict, modified_snapshot: dict) -> dict:
    """전후 스냅샷을 비교해 실제 변경된 필드만 추출한다."""
    changes = {}

    def _compare_values(before_val, after_val, path_key):
        if before_val != after_val:
            changes[path_key] = {"before": before_val, "after": after_val}

    for filename, modified_data in modified_snapshot.items():
        current_data = current_snapshot.get(filename, {})
        if not isinstance(modified_data, list) or not isinstance(current_data, list):
            continue

        # Actors.json, Items.json 등 배열 형태 처리
        for idx, modified_item in enumerate(modified_data):
            if not isinstance(modified_item, dict):
                continue
            if idx >= len(current_data):
                continue
            current_item = current_data[idx]
            if not isinstance(current_item, dict):
                continue

            item_changes = {}
            for field, new_val in modified_item.items():
                old_val = current_item.get(field)
                if old_val != new_val:
                    item_changes[field] = {"before": old_val, "after": new_val}

            if item_changes:
                item_name = modified_item.get("name", f"ID {modified_item.get('id', idx)}")
                changes[f"{filename}[{item_name}]"] = item_changes

    return changes


def build_prompt(state: AgentState) -> list[BaseMessage]:
    intent = state.get("intent", "")
    user_input = state.get("user_input", "")
    passed = state.get("success", True)
    validation_results = state.get("validation_results") or []
    validation_summary = state.get("validation_summary") or ""

    # 스냅샷이 파일 경로면 실제 JSON 데이터로 로드
    current = load_snapshot_payload(state.get("current_game_state"))
    modified = load_snapshot_payload(state.get("modified_game_state"))
    changes = state.get("changes_log") or []

    # 스냅샷 비교로 실제 변경 사항 추출
    actual_changes = []
    if isinstance(current, dict) and isinstance(modified, dict):
        actual_changes = _extract_actual_changes_from_snapshots(current, modified)

    # ── 결과 요약 섹션 구성 ───────────────────────────────
    sections: list[str] = [
        f"## 사용자 원본 요청\n{user_input}",
        f"## 의도\n{intent}",
        f"## 실행 결과\n{'성공' if passed else '실패'}",
    ]

    if validation_summary:
        sections.append(f"## 검증 요약\n{validation_summary}")

    errors = [e for r in validation_results for e in r.get("errors", [])]
    if errors:
        sections.append("## 오류 내용\n" + "\n".join(str(e) for e in errors))

    # 실제 변경 사항이 있으면 우선 표시
    if actual_changes:
        sections.append(
            "## 실제 변경 사항\n" + "\n".join(f"- {change}" for change in actual_changes)
        )

    if changes:
        sections.append("## 실행 이력\n" + json.dumps(changes, ensure_ascii=False, indent=2))

    # 스냅샷이 너무 크면 생략하고 실제 변경 사항만 의존
    if not actual_changes:
        if modified:
            sections.append(
                "## 수정 후 게임 데이터\n" + json.dumps(modified, ensure_ascii=False, indent=2)
            )
        elif current:
            sections.append(
                "## 조회된 게임 데이터\n" + json.dumps(current, ensure_ascii=False, indent=2)
            )

    human_content = "\n\n".join(sections)

    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=human_content),
    ]
