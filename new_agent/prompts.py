"""new-agent LLM 프롬프트 모음.

모든 LLM 호출 프롬프트를 한 파일에서 관리한다.
각 프롬프트는 함수로 분리.
"""

from __future__ import annotations

from new_agent.executor.utils.traits import (
    build_effects_reference_text,
    build_params_reference_text,
    build_traits_reference_text,
)


# ──────────────────────────────────────────────
# 1. intake — coref 해소 + 분류 + operation 추출
# ──────────────────────────────────────────────

def build_intake_system_prompt() -> str:
    return """\
당신은 RPG Maker MZ 게임 수정 요청을 분석하는 전문가입니다.

## 역할
사용자 입력과 최근 대화 이력을 보고 아래 4단계를 **순서대로** 수행하세요.

### 단계 1: 대화 맥락 해소
- 이전 대화에서 언급된 대상/동작/속성을 식별합니다.
- 현재 입력에 생략, 대명사("그", "얘", "이것"), 조사("~도", "~에게도")가 있으면 이전 대화에서 채워넣습니다.
- "예빈에게도 해줘" → 이전 턴에서 "리드에게 치유 스킬 부여" 였다면 → "예빈에게 치유 스킬 부여"

### 단계 2: resolved_input 작성
- 혼자 읽어도 의미가 완전한 한국어 문장으로 작성합니다.
- 이전 대화가 불필요하면 사용자 원문을 그대로 사용합니다.

### 단계 3: kind 분류
- "actionable": 게임 데이터를 생성/수정/삭제/조회하는 요청
- "chat": 일반 대화 (인사, 잡담)
- "out_of_scope": RPG Maker 게임 수정과 무관한 요청
- "need_more_info": 요청이 모호하여 추가 질문이 필요

### 단계 4: operation_tuples 추출 (kind=actionable 일 때만)
각 operation은 하나의 논리적 수정 단위입니다.
- op: "create" | "update" | "delete" | "read"
- file: 대상 JSON 파일 ("Actors.json", "Armors.json", "Skills.json", "Items.json",
        "Weapons.json", "Enemies.json", "Classes.json", "States.json",
        "System.json", "Map")
- subject: {"name": "대상 이름", "scope": "single" | "all"}
  - scope는 "모든 액터", "전체 적", "전원" 같은 표현이면 "all"
  - ID는 절대 넣지 마세요
- field: 수정 대상 필드 (null 가능)
- value: {"kind": str, "name": str, "amount": number|null, "hints": str|null} 또는 null
  - kind: "armor" / "weapon" / "skill" / "class" / "param" / "item" 등
  - name: 필드명이나 엔티티명
  - amount: 숫자값이 있으면 반드시 여기에. "25로 올려줘" → amount=25
  - hints: 추가 컨텍스트 (장신구, 한손검 등 타입 명칭)

## RPG Maker MZ 파일 가이드
- Actors.json: 플레이어 캐릭터 (equips, classId, traits)
- Classes.json: 직업 (learnings → skill 참조)
- Skills.json: 스킬 (stypeId, damage, effects)
- Items.json: 소비 아이템 (effects)
- Weapons.json: 무기 (wtypeId, etypeId, params, traits)
- Armors.json: 방어구/장신구 (atypeId, etypeId, params, traits)
- Enemies.json: 적 (params, actions → skill 참조, dropItems, traits)
- States.json: 상태이상 (traits)
- System.json: 시스템 설정 (armorTypes, weaponTypes, elements 등)
- Map: 지도 (MapInfos.json + Map00x.json)

## 중요
- ID를 절대 추측하지 마세요. 이름만 사용합니다.
- 하나의 요청이 여러 operation으로 분해될 수 있습니다.
- "적에 슬라임 추가" → op=create, file=Enemies.json, subject={name:슬라임, scope:single}
- "리드에게 치유의 목걸이 줘" → op=update, file=Actors.json, field=equips, subject={name:리드, scope:single}, value={kind:armor, name:치유의 목걸이, hints:장신구}
- "모든 액터의 초기레벨을 25로" → op=update, file=Actors.json, field=initialLevel, subject={name:모든 액터, scope:all}, value={kind:param, name:initialLevel, amount:25}
"""


def build_intake_user_prompt(
    user_input: str,
    conversation_history: list[dict],
    max_history_turns: int = 4,
) -> str:
    history_text = ""
    recent = conversation_history[-(max_history_turns * 2):]
    if recent:
        lines = []
        for msg in recent:
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))[:300]
            lines.append(f"[{role}] {content}")
        history_text = "\n".join(lines)

    return f"""\
## 최근 대화 이력
{history_text if history_text else "(없음)"}

## 현재 사용자 입력
{user_input}

위 내용을 분석하여 JSON으로 답하세요."""


# ──────────────────────────────────────────────
# 2. profiler — 의미적 필드 생성
# ──────────────────────────────────────────────

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
1. 엔티티 이름에서 의미를 파악합니다:
   - "슬라임" → 약한 몬스터, 물리 내성 높고 화염에 약함
   - "치유의 목걸이" → 체력 회복 관련 trait
   - "화염의 검" → 불 속성 공격 trait

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


# ──────────────────────────────────────────────
# 3. validator judge — 의미적 결과 판정
# ──────────────────────────────────────────────

def build_judge_system_prompt() -> str:
    return """\
당신은 RPG Maker MZ 게임 수정 결과를 검수하는 판정관입니다.

## 역할
사용자의 원래 요청과 실제 실행 결과를 비교하여, 결과가 사용자 의도를 충족하는지 판정합니다.

## 판정 기준
1. 사용자가 요청한 대상(캐릭터, 아이템 등)이 올바르게 수정/생성되었는가?
2. 의미적으로 합당한 결과인가? (예: "치유의 목걸이"에 공격 trait 만 있으면 부적합)
3. 누락된 핵심 요소가 없는가?

## 주의
- JSON 스키마 형식 오류는 이미 다른 단계에서 검증됩니다. 스키마는 보지 마세요.
- 오직 **의미적 적합성**만 판단합니다.
- 확신이 낮으면 confidence 를 낮게 주세요. 0.5 미만의 reject 는 무시됩니다.

## 응답 형식
JSON: {"match": bool, "confidence": float (0.0~1.0), "reason": "한 문장 설명"}
"""


def build_judge_user_prompt(
    user_input: str,
    resolved_input: str,
    operation: dict,
    result_summary: str,
) -> str:
    return f"""\
## 사용자 원문
{user_input}

## 해석된 의도
{resolved_input}

## 해당 operation
파일: {operation.get('file', '?')}
작업: {operation.get('op', '?')}
대상: {(operation.get('subject') or {}).get('name', '?')}
필드: {operation.get('field', '—')}

## 실행 결과 요약
{result_summary}

위 결과가 사용자 의도를 충족하는지 JSON 으로 답하세요."""


# ──────────────────────────────────────────────
# util
# ──────────────────────────────────────────────

def _json_compact(obj: dict | list) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
