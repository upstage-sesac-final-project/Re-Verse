"""profiler 프롬프트 빌더.

create step 의 빈 필드를 LLM 으로 채우기 위한 프롬프트.
"""

from __future__ import annotations

import json

from agent.utils.traits_reference import (
    build_effects_reference_text,
    build_params_reference_text,
    build_traits_reference_text,
)


def build_profiler_system_prompt() -> str:
    traits_ref = build_traits_reference_text()
    effects_ref = build_effects_reference_text()
    params_ref = build_params_reference_text()

    return f"""\
당신은 RPG Maker MZ 게임 엔티티 디자이너입니다.

## 역할
새로 생성될 엔티티의 이름과 기본 정보를 받아, 해당 엔티티에 어울리는
params, traits, effects, description 등의 필드를 **RPG Maker MZ 포맷**으로 채웁니다.

## 핵심 원칙
1. 엔티티 이름에서 의미를 파악합니다.
2. RPG 세계관에 맞는 합리적인 수치를 사용합니다.
3. 반드시 아래 코드표에 맞는 code/dataId/value 를 사용합니다.

{traits_ref}

{effects_ref}

{params_ref}

## 응답 규칙
- target_info 의 기존 필드(name, id 등)는 유지합니다.
- 비어 있는 필드만 채웁니다.
- params 는 반드시 8개 정수 배열 [HP, MP, ATK, DEF, MAT, MDF, AGI, LUK] 로 제공합니다.
- traits 는 [{{"code": int, "dataId": int, "value": number}}, ...] 배열입니다.
- effects 는 [{{"code": int, "dataId": int, "value1": number, "value2": number}}, ...] 배열입니다.
- description 은 한국어로, 1~2문장으로 작성합니다.
- 기존 엔트리 예시는 포맷 참고용입니다. 값을 그대로 복사하지 마세요.
- **엔티티 이름에서 유형을 판단하세요**:
  - 방어구: "목걸이/반지/귀걸이" → etypeId=5(장신구), "갑옷/로브" → etypeId=4(몸), "투구/왕관" → etypeId=3(머리), "방패" → etypeId=2(방패)
  - 무기: "검/도" → wtypeId=2, "단검" → wtypeId=1, "지팡이" → wtypeId=6
- 스키마 레퍼런스에 정의된 유효 범위를 반드시 지키세요.
"""


def build_profiler_user_prompt(
    step: dict,
    schema_excerpt: str,
    examples: list[dict] | None = None,
    feedback: str | None = None,
    user_input: str | None = None,
    parsed_command: dict | None = None,
) -> str:
    target_file = step.get("target_file", "")
    target_info = step.get("target_info", {})
    name = target_info.get("name", "?")

    parts = [
        f"## 생성 대상\n파일: {target_file}\n이름: {name}",
    ]

    # Task 28 — 유저 원문 요청 최우선 주입. LLM 이 template default 로 빠지지 않도록.
    if user_input:
        parts.append(
            f"\n## 유저 원문 요청 (최우선 참조)\n> {user_input}\n"
            f"위 요청의 의도·어휘·수치를 엔티티 설계에 반영하세요."
        )

    if parsed_command:
        pc_summary = _format_parsed_command(parsed_command)
        if pc_summary:
            parts.append(
                f"\n## 유저가 명시한 필드 (절대 무시 금지)\n{pc_summary}\n"
                f"위 필드는 이미 target_info 에 반영됐거나 반영 예정입니다. 다른 기본값으로 덮지 마세요."
            )

    parts.append(f"\n## 현재 target_info\n```json\n{_json_compact(target_info)}\n```")

    if schema_excerpt:
        parts.append(f"\n## 스키마 참고\n{schema_excerpt}")

    if examples:
        ex_text = "\n".join(_json_compact(e) for e in examples[:2])
        parts.append(f"\n## 기존 엔트리 예시\n{ex_text}")

    if feedback:
        parts.append(f"\n## 이전 시도 실패 피드백\n{feedback}\n위 피드백을 참고하여 수정하세요.")

    parts.append(
        "\n비어 있는 필드를 채워서 완성된 target_info 를 JSON 으로 답하세요. "
        "target_info 의 이름·이미지 필드 등 이미 채워진 값은 **절대 변경 금지**."
    )

    return "\n".join(parts)


def _format_parsed_command(pc: dict) -> str:
    """parsed_command 를 프롬프트 친화적 요약 문자열로 변환."""
    lines: list[str] = []
    field = (pc.get("field") or "").strip()
    target = (pc.get("target") or "").strip()
    if field:
        lines.append(f"- 카테고리: {field}")
    if target:
        lines.append(f"- 대상 이름: {target}")
    prop = (pc.get("property") or "").strip()
    val = str(pc.get("value") or "").strip()
    if prop and val:
        lines.append(f"- 명시 속성: {prop} = {val}")
    for extra in pc.get("additional_properties") or []:
        if not isinstance(extra, dict):
            continue
        ep = (extra.get("property") or "").strip()
        ev = str(extra.get("value") or "").strip()
        if ep and ev:
            lines.append(f"- 명시 속성: {ep} = {ev}")
    return "\n".join(lines)


def _json_compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
