"""Synthesizer 프롬프트 — 실행 결과를 사용자 친화적 응답으로 변환."""

import json

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


def build_prompt(state: AgentState) -> list[BaseMessage]:
    intent = state.get("intent", "")
    user_input = state.get("user_input", "")
    validation = state.get("validation_result") or {}
    passed = validation.get("passed", True)
    errors = validation.get("errors") or []
    current = state.get("current_game_state") or {}
    modified = state.get("modified_game_state") or {}
    changes = state.get("changes_log") or []

    # ── 결과 요약 섹션 구성 ───────────────────────────────
    sections: list[str] = [
        f"## 사용자 원본 요청\n{user_input}",
        f"## 의도\n{intent}",
        f"## 실행 결과\n{'성공' if passed else '실패'}",
    ]

    if errors:
        sections.append("## 오류 내용\n" + "\n".join(str(e) for e in errors))

    if changes:
        sections.append("## 변경 이력\n" + json.dumps(changes, ensure_ascii=False, indent=2))

    if modified:
        sections.append(
            "## 수정 후 게임 데이터\n" + json.dumps(modified, ensure_ascii=False, indent=2)
        )
    elif current:
        # 조회 시나리오: current_game_state에 조회 결과가 담길 수 있음
        sections.append(
            "## 조회된 게임 데이터\n" + json.dumps(current, ensure_ascii=False, indent=2)
        )

    if current and modified:
        sections.append(
            "## 수정 전 게임 데이터 (비교용)\n" + json.dumps(current, ensure_ascii=False, indent=2)
        )

    human_content = "\n\n".join(sections)

    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=human_content),
    ]
