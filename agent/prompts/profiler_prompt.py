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
) -> str:
    target_file = step.get("target_file", "")
    target_info = step.get("target_info", {})
    name = target_info.get("name", "?")

    parts = [
        f"## 생성 대상\n파일: {target_file}\n이름: {name}",
        f"\n## 현재 target_info\n```json\n{_json_compact(target_info)}\n```",
    ]

    if schema_excerpt:
        parts.append(f"\n## 스키마 참고\n{schema_excerpt}")

    if examples:
        ex_text = "\n".join(_json_compact(e) for e in examples[:2])
        parts.append(f"\n## 기존 엔트리 예시\n{ex_text}")

    if feedback:
        parts.append(f"\n## 이전 시도 실패 피드백\n{feedback}\n위 피드백을 참고하여 수정하세요.")

    parts.append(
        "\n비어 있는 필드를 채워서 완성된 target_info 를 JSON 으로 답하세요."
    )

    return "\n".join(parts)


def _json_compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
