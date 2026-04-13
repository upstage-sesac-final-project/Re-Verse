# LLM 프롬프트 설계 가이드

> A. 기획자(game_designer)와 F. 이벤트 기획자(event_planner)의 프롬프트 상세
> 나머지 에셋 프롬프트는 `asset_generation.md` 참조

---

## 개요

Full Generation에서 LLM 호출이 가장 중요한 두 노드:

| 노드 | 중요도 | 이유 |
|------|--------|------|
| A. 기획자 | **최고** | 게임 전체 구조를 결정. 잘못 설계되면 모든 후속 노드가 실패 |
| F. 이벤트 기획자 | **높음** | 플레이어가 실제로 경험하는 스토리·이벤트를 결정 |

---

## A. 기획자 — game_designer_prompt.py

### 역할

`user_input`을 받아 `GameSpec` JSON을 생성한다.
이 JSON이 이후 모든 노드의 입력이 된다.

### 프롬프트 설계 원칙

1. **구조화된 출력 강제**: Pydantic 스키마를 JSON Schema로 변환해서 포함
2. **수량 범위 명시**: "캐릭터 2~4명"처럼 범위를 구체적으로 지정
3. **의존성 명시**: maps의 connects_to 필드가 name 문자열 참조임을 강조
4. **플레이타임 제한**: 5~10분 분량의 콘텐츠 양을 구체적 수치로 안내

### 전체 프롬프트

```python
# agent/generation/prompts/game_designer_prompt.py
import json
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


_SYSTEM = """\
당신은 RPG Maker MZ 게임 기획자입니다.
사용자 요청을 받아 5~10분 플레이타임의 완성된 RPG 게임 기획서를 JSON으로 작성하세요.

## 출력 규칙

반드시 아래 JSON 스키마를 정확히 따르세요. 추가 설명 없이 JSON만 출력하세요.

```json
{
  "title": "게임 제목",
  "theme": "세계관 설명 (1~2문장)",
  "playtime_minutes": 7,
  "story": {
    "synopsis": "전체 줄거리 (2~3문장)",
    "acts": ["1막: ...", "2막: ...", "3막: ..."]
  },
  "characters": [
    {
      "name": "캐릭터 이름",
      "class_name": "직업 이름",
      "role": "주인공",
      "personality": "성격 설명 (1문장)"
    }
  ],
  "enemies": [
    {
      "name": "적 이름",
      "tier": "weak",
      "location": "어느 맵에 등장하는지"
    }
  ],
  "maps": [
    {
      "name": "맵 이름",
      "type": "town",
      "description": "맵 설명 (1문장)",
      "connects_to": ["연결된 맵 이름"]
    }
  ],
  "key_items": ["핵심 아이템 이름"],
  "skills": ["스킬 이름 목록"]
}
```

## 수량 기준 (5~10분 분량)

| 요소 | 최소 | 최대 |
|------|------|------|
| 캐릭터 (character) | 2 | 4 |
| 직업 (class_name 종류) | 2 | 4 |
| 스킬 (skills) | 8 | 15 |
| 적 (enemies) | 5 | 10 |
| 맵 (maps) | 3 | 4 |
| 아이템 (key_items) | 5 | 10 |

## 역할 허용값
  role: "주인공" | "서포터" | "딜러" | "탱커"
  (주인공은 반드시 1명)

## 적 티어 허용값
  tier: "weak" | "normal" | "elite" | "boss"
  (boss는 반드시 1종, 마지막 맵에 배치)

## 맵 타입 허용값
  type: "town" | "dungeon" | "boss" | "field"
  (town 1개 이상, boss 1개 필수)

## 맵 연결 규칙
  - connects_to에는 반드시 다른 맵의 name을 사용
  - 모든 맵이 시작 맵(첫 번째 town)에서 도달 가능해야 함
  - 고립된 맵 금지

## 스킬 설계 원칙
  - 물리 공격, 마법 공격, 회복 스킬을 균형 있게 포함
  - 각 캐릭터가 2~4개 스킬 사용 가능한 수준
"""


def build_game_designer_prompt(user_input: str) -> list[BaseMessage]:
    human = f"""\
사용자 요청:
{user_input}

위 요청을 바탕으로 GameSpec JSON을 생성하세요.
JSON 외의 텍스트(설명, 마크다운 코드블록 등)는 포함하지 마세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
```

### 파싱 및 폴백

```python
# agent/generation/nodes/game_designer.py
from pydantic import ValidationError
from agent.generation.prompts.game_designer_prompt import build_game_designer_prompt
from agent.models.game_spec import GameSpec


async def game_designer(state: GenerationState) -> GenerationState:
    gen_id = state["generation_id"]

    await publish_progress(gen_id, {
        "type": "progress", "phase": "spec", "progress": 2,
        "message": "게임 기획 중...",
    })

    for attempt in range(3):
        raw = await invoke_llm(build_game_designer_prompt(state["user_input"]))

        try:
            # JSON 블록 추출 (LLM이 마크다운으로 감쌀 때 대비)
            json_str = _extract_json(raw)
            spec_dict = json.loads(json_str)
            spec = GameSpec.model_validate(spec_dict)

            # 맵 연결성 사전 검증
            _validate_map_connections(spec)

            await publish_progress(gen_id, {
                "type": "phase_complete",
                "phase": "spec",
                "summary": (
                    f"'{spec.title}' — 맵 {len(spec.maps)}개, "
                    f"캐릭터 {len(spec.characters)}명, "
                    f"적 {len(spec.enemies)}종"
                ),
            })

            return {**state, "game_spec": spec, "completed_phases": [..., "spec"]}

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("GameSpec 파싱 실패 attempt=%d: %s", attempt + 1, e)

    raise GenerationError("게임 기획 3회 실패")


def _extract_json(text: str) -> str:
    """LLM 출력에서 JSON 부분만 추출."""
    # 마크다운 코드블록 제거
    if "```json" in text:
        start = text.index("```json") + 7
        end   = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        start = text.index("```") + 3
        end   = text.index("```", start)
        return text[start:end].strip()
    # 중괄호로 시작/끝 추출
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]
    return text


def _validate_map_connections(spec: GameSpec) -> None:
    """모든 맵이 시작 맵에서 도달 가능한지 BFS로 확인."""
    map_names = {m.name for m in spec.maps}
    graph: dict[str, set[str]] = {m.name: set(m.connects_to) for m in spec.maps}

    start = spec.maps[0].name
    visited = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(graph.get(current, set()) - visited)

    unreachable = map_names - visited
    if unreachable:
        raise ValueError(f"고립된 맵: {unreachable} — connects_to를 수정하세요")
```

### 흔한 실패 패턴 & 대응

| 실패 패턴 | 원인 | 대응 |
|---------|------|------|
| JSON 외 텍스트 포함 | LLM 설명 추가 | `_extract_json()`으로 추출 |
| `connects_to`에 존재하지 않는 맵 이름 | LLM 환각 | `_validate_map_connections()` 재시도 유도 |
| boss 없음 | LLM이 tier 생략 | 검증 시 강제 추가 또는 재시도 |
| 캐릭터 role이 모두 "주인공" | LLM 오해 | 프롬프트에 "주인공은 반드시 1명" 명시 |
| skills 배열 비어있음 | LLM 생략 | 폴백: 기본 스킬 목록 삽입 |

---

## F. 이벤트 기획자 — event_planner_prompt.py

### 역할

맵 1개의 `MapSpec`을 받아 해당 맵의 DSL 이벤트 목록(YAML)을 생성한다.
맵당 1회 호출, 3개 맵이면 3회 병렬 호출.

### 프롬프트 설계 원칙

1. **이름 기반**: 스위치·아이템·맵은 이름으로 작성 (번호 사용 금지)
2. **좌표 제한**: 맵 크기 내 좌표만 사용 (x < width, y < height)
3. **스토리 일관성**: game_spec의 스토리 문맥을 포함해서 LLM이 어긋나지 않도록
4. **Few-shot 예시**: 정확한 DSL 형식을 보여주는 예시 2~3개 포함
5. **연결점 명시**: 출구/입구 좌표를 직접 제시 (R4 방지)

### 전체 프롬프트

```python
# agent/generation/prompts/event_planner_prompt.py
import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


_SYSTEM = """\
당신은 RPG Maker MZ 이벤트 기획자입니다.
맵 명세를 받아 해당 맵의 이벤트를 YAML DSL로 작성하세요.

## DSL 타입 및 필수 필드

### npc (NPC 대화)
```yaml
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: npc
  trigger: action_button  # action_button | player_touch | auto_run
  dialogue:
    - "대사 1"
    - "대사 2"
  condition:              # 선택 (조건부 대화)
    switch: {스위치 이름}
    value: false
  set_switch: {스위치 이름}  # 선택 (대화 후 ON)
```

### transfer (맵 이동)
```yaml
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: transfer
  trigger: player_touch
  to_map: {맵 이름}
  to_x: {정수}
  to_y: {정수}
  set_switch: {스위치 이름}  # 선택
```

### chest (보물 상자)
```yaml
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: chest
  item: {아이템 이름}
  item_type: item  # item | weapon | armor | gold
  amount: {정수}
  one_time: true
  chest_switch: {스위치 이름}
  dialogue_before: "상자 발견 대사"
  dialogue_after:  "아이템 획득 대사"
```

### battle (전투)
```yaml
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: battle
  trigger: player_touch
  troop: {적 그룹 이름}
  escape_allowed: true
  lose_condition: game_over  # game_over | continue
  on_win:
    - give_item: { item: {아이템 이름}, amount: 1 }
    - set_switch: {스위치 이름}
  one_time: true
  battle_switch: {스위치 이름}
```

### shop (상점)
```yaml
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: shop
  trigger: action_button
  dialogue: "상점 인사 대사"
  items:
    - { item: {아이템 이름}, item_type: item }
    - { item: {무기 이름},   item_type: weapon }
```

## 절대 금지 사항

- 스위치·아이템·맵을 번호(숫자)로 지정 금지 → 반드시 이름(문자열) 사용
- x, y 좌표가 맵 크기를 벗어나는 것 금지
- 동일한 (x, y)에 이벤트 2개 배치 금지
- to_map에 존재하지 않는 맵 이름 사용 금지

## 출력 형식

YAML만 출력하세요. 설명, 마크다운 코드블록 불필요.

events:
  - ...
  - ...
"""


def build_event_planner_prompt(
    map_spec: "MapSpec",
    game_spec: "GameSpec",
    id_table: "IdTable",
    switch_table: "SwitchTable",
    connection_info: "MapConnectionInfo",
) -> list[BaseMessage]:
    # 이 맵과 관련된 ID만 필터링 (컨텍스트 절약, R5 방지)
    relevant_items   = list(id_table.items.keys())
    relevant_weapons = list(id_table.weapons.keys())
    relevant_armors  = list(id_table.armors.keys())
    relevant_troops  = list(id_table.troops.keys())
    relevant_maps    = list(id_table.maps.keys())

    # 미리 사용할 switch 이름 목록
    existing_switches = list(switch_table.switches.keys())

    # 연결점 정보 (R4 방지용)
    exit_info_lines = []
    for to_map_id, (ex, ey) in connection_info.exit_points.items():
        to_map_name = next(
            (name for name, mid in id_table.maps.items() if mid == to_map_id),
            f"Map{to_map_id}"
        )
        # 목적지 맵의 spawn_point 조회
        dest_spawn = _get_spawn_for_map(to_map_id)  # connection_info에서 조회
        exit_info_lines.append(
            f"- 이 맵 출구 좌표: ({ex}, {ey}) → '{to_map_name}' 맵으로\n"
            f"  '{to_map_name}' 맵 도착 좌표: to_x={dest_spawn[0]}, to_y={dest_spawn[1]}"
        )

    human = f"""\
## 맵 정보
이름: {map_spec.name}
타입: {map_spec.map_type}
크기: 가로={map_spec.width}, 세로={map_spec.height}  ← x는 0~{map_spec.width - 1}, y는 0~{map_spec.height - 1}
분위기: {map_spec.atmosphere}

## 랜드마크 (이벤트 배치 위치 힌트)
{chr(10).join(
    f"- {lm.name} ({lm.position_hint})" + (f" — NPC: {lm.npc}" if lm.npc else "")
    for lm in map_spec.landmarks
)}

## 맵 연결 정보 (transfer 이벤트에 반드시 이 좌표 사용)
{chr(10).join(exit_info_lines) if exit_info_lines else "없음 (이 맵은 출구 없음)"}

## 스토리 컨텍스트
{game_spec.story['synopsis']}
현재 맵의 역할: {map_spec.description}

## 사용 가능한 이름 목록 (이 목록에 없는 이름 사용 금지)

스위치 이름:
{chr(10).join(f"  - {s}" for s in existing_switches)}

아이템: {', '.join(relevant_items[:10])}
무기:   {', '.join(relevant_weapons[:5])}
방어구: {', '.join(relevant_armors[:5])}
적 그룹: {', '.join(relevant_troops)}
이동 가능한 맵: {', '.join(relevant_maps)}

## 이벤트 생성 가이드

이 맵에 배치해야 할 이벤트:
{ _describe_required_events(map_spec) }

YAML 출력:
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]


def _describe_required_events(map_spec: "MapSpec") -> str:
    """맵 타입별 권장 이벤트 목록."""
    if map_spec.map_type == "town":
        return """\
1. NPC 대화 (랜드마크마다 1개, 조건부 대화 권장)
2. 상점 이벤트 (상점 랜드마크가 있으면)
3. 맵 이동 이벤트 (exits 수만큼, 위 좌표 정보 사용)
4. 선택: 안내판, 보물 상자 1개"""

    elif map_spec.map_type == "dungeon":
        return """\
1. 맵 이동 이벤트 (입구/출구, 위 좌표 정보 사용)
2. 전투 이벤트 2~3개 (player_touch 트리거, one_time=true)
3. 보물 상자 1~2개
4. 선택: 보스 전투 안내 NPC"""

    elif map_spec.map_type == "boss":
        return """\
1. 보스 전투 이벤트 (lose_condition: game_over)
2. 보스 처치 후 엔딩 대사 (auto_run, condition: boss_defeated=true)
3. 맵 이동 이벤트 (탈출용)"""

    return "맵 타입에 맞는 적절한 이벤트 3~5개"
```

### Few-shot 예시 (프롬프트 내 포함)

시스템 프롬프트 끝에 아래를 추가:

```python
_SYSTEM += """
## 정확한 출력 예시

events:
  - x: 8
    y: 3
    name: 여관주인
    type: npc
    trigger: action_button
    dialogue:
      - "어서오세요, 용사여!"
      - "이 마을은 요즘 몬스터 때문에 큰일이에요."
    condition:
      switch: boss_defeated
      value: false

  - x: 8
    y: 12
    name: 던전_입구
    type: transfer
    trigger: player_touch
    to_map: 어둠의 던전
    to_x: 10
    to_y: 13
    set_switch: dungeon_entered

  - x: 14
    y: 5
    name: 보물상자_01
    type: chest
    item: 회복 포션
    item_type: item
    amount: 2
    one_time: true
    chest_switch: chest_1_01
    dialogue_before: "낡은 상자가 있다."
    dialogue_after: "회복 포션을 2개 손에 넣었다!"
"""
```

### 파싱 & 좌표 검증

```python
async def event_planner(state: GenerationState) -> GenerationState:
    gen_id = state["generation_id"]

    # 맵별로 병렬 실행
    tasks = [
        _plan_single_map(
            map_spec=spec,
            game_spec=state["game_spec"],
            id_table=state["id_table"],
            switch_table=state["switch_table"],
            connection_info=state["connection_info"][spec.map_id],
        )
        for spec in state["map_specs"]
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    event_dsl: dict[int, list] = {}
    for spec, result in zip(state["map_specs"], results):
        if isinstance(result, Exception):
            logger.error("Map%d 이벤트 기획 실패: %s", spec.map_id, result)
            result = _fallback_events(spec, state["id_table"])
        event_dsl[spec.map_id] = result

    return {**state, "event_dsl": event_dsl, ...}


async def _plan_single_map(map_spec, game_spec, id_table, switch_table, connection_info):
    for attempt in range(3):
        prompt  = build_event_planner_prompt(
            map_spec, game_spec, id_table, switch_table, connection_info
        )
        raw_yaml = await invoke_llm(prompt)

        events = parse_dsl_safe(raw_yaml, map_spec.map_id)
        if events is None:
            continue

        # 좌표 범위 검증
        valid_events = validate_event_coords(events, map_spec)

        # 이름 참조 검증 (id_table에 없는 이름 사용 여부)
        valid_events = validate_name_references(valid_events, id_table, switch_table)

        if valid_events:
            return valid_events

    return _fallback_events(map_spec, id_table)
```

---

## 프롬프트 공통 유틸리티

```python
# agent/generation/prompts/utils.py

def _extract_json(text: str) -> str:
    """LLM 출력에서 JSON 객체 추출."""
    if "```json" in text:
        s = text.index("```json") + 7
        e = text.index("```", s)
        return text[s:e].strip()
    if "```" in text:
        s = text.index("```") + 3
        e = text.index("```", s)
        return text[s:e].strip()
    s = text.find("{")
    e = text.rfind("}") + 1
    return text[s:e] if s >= 0 else text


def _extract_yaml(text: str) -> str:
    """LLM 출력에서 YAML 추출."""
    if "```yaml" in text:
        s = text.index("```yaml") + 7
        e = text.index("```", s)
        return text[s:e].strip()
    if "```" in text:
        s = text.index("```") + 3
        e = text.index("```", s)
        return text[s:e].strip()
    # YAML은 "events:" 로 시작하는 부분부터
    if "events:" in text:
        return text[text.index("events:"):].strip()
    return text
```

---

## 토큰 관리 전략

| 프롬프트 | 시스템 토큰 | 사용자 토큰 | 출력 토큰 | 합계 |
|---------|-----------|-----------|---------|------|
| game_designer | ~600 | ~100 | ~700 | ~1,400 |
| asset_generator (actors) | ~500 | ~400 | ~800 | ~1,700 |
| map_designer | ~400 | ~600 | ~500 | ~1,500 |
| event_planner (맵당) | ~800 | ~600 | ~600 | ~2,000 |

**Solar Pro 2 컨텍스트 한계: 32,768 토큰** → 모든 호출이 안전 범위.

### 절약 전략

1. `id_table` 전체를 넣지 않고 관련 항목만 필터링 (R5 완화)
2. `game_spec` 전체 대신 `synopsis` + 현재 맵 관련 정보만 포함
3. `few-shot` 예시는 타입당 1개로 유지

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- DSL 명세 (컴파일 결과): `docs/The_world/dsl_specification.md`
- 에셋 프롬프트: `docs/The_world/asset_generation.md`
- 리스크 R2 (DSL 파싱 실패): `docs/The_world/risks_and_mitigations.md#r2`
- 리스크 R4 (좌표 불일치): `docs/The_world/risks_and_mitigations.md#r4`
- 리스크 R5 (컨텍스트 초과): `docs/The_world/risks_and_mitigations.md#r5`
