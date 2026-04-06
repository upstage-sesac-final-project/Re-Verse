# 리스크 분석 및 완화 전략

> Full Generation 시스템의 10가지 주요 리스크와 구체적 대응 방안

---

## 리스크 우선순위 매트릭스

| # | 리스크 | 발생 가능성 | 영향도 | 우선순위 |
|---|--------|-----------|--------|---------|
| R1 | ID 참조 오류 | 높음 | 심각 | **P0** |
| R2 | DSL 파싱 실패 | 높음 | 심각 | **P0** |
| R3 | 스위치 번호 충돌 | 중간 | 심각 | **P1** |
| R4 | 맵 좌표 연결 불일치 | 중간 | 높음 | **P1** |
| R5 | 컨텍스트 길이 초과 | 낮음 | 중간 | **P2** |
| R6 | 생성 실패 복구 | 높음 | 중간 | **P2** |
| R7 | 밸런스 자동 검증 불가 | 중간 | 중간 | **P2** |
| R8 | 비용 (LLM 호출 수) | 중간 | 낮음 | **P3** |
| R9 | DSL 커버리지 한계 | 높음 | 낮음 | **P3** |
| R10 | 타일 품질 | 낮음 | 낮음 | **P3** |

---

## R1. ID 참조 오류 (P0 — 즉시 해결 필수)

### 문제 설명

병렬로 에셋을 생성할 때, LLM이 다른 에셋의 ID를 참조해야 하는 경우가 많다.
ID 테이블이 사전에 확정되지 않으면 잘못된 값이 들어간다.

### 구체적 실패 시나리오

```
시나리오 1: classId 오염
  Actor "해럴드" 생성 시 → classId: ? (전사 클래스가 아직 생성 안 됨)
  → LLM이 classId: 0 기본값 사용
  → 게임에서 해럴드가 "직업 없음" 상태로 생성

시나리오 2: weaponTypeId 오염
  Weapon "철검" 생성 시 → wtypeId: ? (WeaponType 목록 모름)
  → LLM이 wtypeId: 1 임의 선택
  → 의도한 무기 유형이 아닌 엉뚱한 타입 배정

시나리오 3: learnAt skillId 오염
  Actor의 초기 스킬 목록 → skillId: ?
  → LLM이 존재하지 않는 ID 사용 (예: skillId: 99)
  → 캐릭터 장비 페이지에서 빈 슬롯 또는 오류
```

### 완화 전략

#### 1차: B(설계사)에서 ID 사전 확정 (필수)

```python
# asset_planner.py
def build_id_table(game_spec: GameSpec) -> IdTable:
    """
    LLM 호출 없이 game_spec의 이름 목록만 보고
    각 에셋의 ID를 1부터 순서대로 할당.
    ID는 생성 전에 완전히 확정되어야 한다.
    """
    id_table = IdTable()

    # RPG Maker MZ는 인덱스 0이 비어있으므로 ID는 1부터 시작
    for i, name in enumerate(game_spec.character_names, start=1):
        id_table.actors[name] = i

    for i, name in enumerate(game_spec.class_names, start=1):
        id_table.classes[name] = i

    # ... (skills, items, weapons, armors, enemies, troops, maps)
    return id_table
```

#### 2차: LLM 프롬프트에 ID 명시

```
# LLM 프롬프트 예시 (actor 생성)
해럴드 캐릭터를 생성하세요.

반드시 다음 ID를 사용하세요 (임의 변경 금지):
- actor_id: 1
- classId: 1  ← 전사 클래스
- 초기 스킬 id 목록: [1, 2]  ← 슬래시(1), 방어(2)

이 외의 ID를 사용하면 게임이 작동하지 않습니다.
```

#### 3차: 생성 후 ID 검증 (I. 검증기)

```python
def check_id_references(assets: dict, id_table: IdTable) -> list[str]:
    errors = []
    valid_class_ids  = set(id_table.classes.values())
    valid_skill_ids  = set(id_table.skills.values())
    valid_weapon_ids = set(id_table.weapons.values())

    for actor in assets.get("Actors.json", []):
        if not actor:
            continue
        if actor.get("classId") not in valid_class_ids:
            errors.append(
                f"[R1] Actor '{actor['name']}': classId={actor['classId']} 없음"
            )
        for skill_id in actor.get("skills", []):
            if skill_id and skill_id not in valid_skill_ids:
                errors.append(
                    f"[R1] Actor '{actor['name']}': skillId={skill_id} 없음"
                )
    return errors
```

---

## R2. DSL 파싱 실패 (P0 — 즉시 해결 필수)

### 문제 설명

LLM이 올바른 YAML/JSON이 아닌 DSL을 출력하거나, 필수 필드를 누락하거나,
DSL 스키마와 다른 필드명을 사용하는 경우.

### 구체적 실패 시나리오

```
시나리오 1: 필드명 오류
  기대: type: transfer
  실제: type: "맵 이동"   ← 영어 대신 한국어 사용
  → Pydantic 검증 실패, 해당 이벤트 무시됨

시나리오 2: 필수 필드 누락
  기대: to_map: 2, to_x: 8, to_y: 1
  실제: to_map: 2          ← to_x, to_y 없음
  → 이벤트 컴파일러에서 AttributeError

시나리오 3: YAML 문법 오류
  기대: dialogue: ["안녕!", "잘 가!"]
  실제: dialogue: ["안녕!", 잘 가!]  ← 따옴표 누락
  → yaml.YAMLError 발생, 전체 맵 이벤트 실패

시나리오 4: 좌표 범위 초과
  기대: x: 5, y: 3 (17×13 마을 맵)
  실제: x: 25, y: 30  ← 맵 크기 초과
  → 이벤트가 맵 밖에 배치됨
```

### 완화 전략

#### 1차: Pydantic 검증 + 즉시 재시도

```python
# event_planner.py
async def plan_events_for_map(
    map_spec: MapSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    max_retries: int = 3,
) -> list[DslEvent]:
    for attempt in range(max_retries):
        raw_yaml = await invoke_llm(build_event_prompt(map_spec, id_table))
        events = parse_dsl_safe(raw_yaml, map_spec.map_id)

        if events is not None:
            return events

        logger.warning(
            "DSL 파싱 실패 map_id=%d attempt=%d/%d",
            map_spec.map_id, attempt + 1, max_retries
        )

    # 모든 재시도 실패 → 최소 이벤트만 생성 (맵 이동만)
    logger.error("DSL 파싱 3회 실패, 최소 이벤트로 대체 map_id=%d", map_spec.map_id)
    return build_fallback_events(map_spec, id_table)


def parse_dsl_safe(raw_yaml: str, map_id: int) -> list[DslEvent] | None:
    try:
        data = yaml.safe_load(raw_yaml)
        if not isinstance(data, dict):
            raise ValueError("YAML 루트가 dict가 아님")
        events_raw = data.get("events", [])
        return [DslEvent.model_validate(e) for e in events_raw]
    except (yaml.YAMLError, ValidationError, ValueError) as e:
        logger.warning("DSL 파싱 실패 map_id=%d: %s", map_id, e)
        return None
```

#### 2차: Few-shot 예시를 항상 포함

프롬프트에 다음 형식의 예시를 항상 포함한다:

```yaml
# 프롬프트 내 few-shot 예시
events:
  - x: 8
    y: 3
    name: 여관주인
    type: npc                      # type은 반드시 영어 소문자
    trigger: action_button
    dialogue:
      - "어서오세요!"               # 대화 텍스트는 반드시 따옴표 포함

  - x: 8
    y: 12
    name: 던전_입구
    type: transfer                 # npc / transfer / chest / battle / shop
    trigger: player_touch
    to_map: 어둠의 던전             # 맵 이름 (ID 아님)
    to_x: 8
    to_y: 1
```

#### 3차: 좌표 범위 검증

```python
def validate_event_coords(events: list[DslEvent], map_spec: MapSpec) -> list[DslEvent]:
    valid = []
    for event in events:
        if 0 <= event.x < map_spec.width and 0 <= event.y < map_spec.height:
            valid.append(event)
        else:
            logger.warning(
                "이벤트 '%s' 좌표 범위 초과: (%d, %d) / 맵 크기 %d×%d",
                event.name, event.x, event.y, map_spec.width, map_spec.height
            )
    return valid
```

#### 폴백(Fallback) 이벤트

파싱이 3회 모두 실패하면 최소한의 기능적 이벤트만 생성:

```python
def build_fallback_events(map_spec: MapSpec, id_table: IdTable) -> list[DslEvent]:
    """파싱 실패 시 최소 이벤트 (맵 이동만 보장)"""
    events = []
    for exit_spec in map_spec.exits:
        ex, ey = get_exit_position(exit_spec.direction, map_spec.width, map_spec.height)
        events.append(TransferEvent(
            type="transfer",
            x=ex, y=ey,
            name=f"exit_to_{exit_spec.to_map_id}",
            to_map_id=exit_spec.to_map_id,
            to_x=5, to_y=5,   # 안전한 기본 좌표
        ))
    return events
```

---

## R3. 스위치/변수 번호 충돌 (P1)

### 문제 설명

여러 맵의 이벤트 기획자가 병렬로 실행되면서 같은 스위치 번호를 다른 의미로 사용할 수 있다.

### 구체적 실패 시나리오

```
맵1 이벤트 기획자: switch 3 = "town_npc_talked"
맵2 이벤트 기획자: switch 3 = "dungeon_entered"   ← 같은 번호, 다른 의미

결과:
  마을 NPC와 대화하면 switch 3 = ON
  던전 입구에서 switch 3이 ON인지 확인 → 이미 ON
  → 던전에 처음 들어가는 것이 자동으로 인식됨 (버그)
```

### 완화 전략

#### 1차: B(설계사)에서 스위치 전체 사전 할당

```python
def build_switch_table(game_spec: GameSpec, map_specs: list[MapSpec]) -> SwitchTable:
    """
    스토리 흐름에서 필요한 스위치를 미리 파악해서 번호 할당.
    이벤트 기획자는 스위치 '이름'만 사용하고 번호는 모른다.
    """
    table = SwitchTable()

    # 게임 흐름의 핵심 스위치 (스토리 분기)
    core_switches = [
        "boss_defeated",
        "dungeon_entered",
        "game_ending_triggered",
    ]

    # 맵별 스위치 (NPC 대화, 상자 등)
    for map_spec in map_specs:
        for landmark in map_spec.landmarks:
            if landmark.npc:
                core_switches.append(f"{landmark.name}_npc_talked")
        for i in range(5):   # 맵당 최대 5개 상자 예상
            core_switches.append(f"chest_{map_spec.map_id}_{i:02d}")

    # ID 할당
    for i, name in enumerate(core_switches, start=1):
        table.switches[name] = i
        table.next_switch_id = i + 1

    return table
```

#### 2차: 이름 기반 사용 강제

```python
# event_planner.py 프롬프트 규칙
"""
스위치를 사용할 때 반드시 이름(문자열)으로 작성하세요.
번호(숫자)를 직접 쓰지 마세요.

올바른 예:
  set_switch: dungeon_entered      ✅

잘못된 예:
  set_switch: 3                    ❌  (번호 직접 사용 금지)
"""
```

#### 3차: 컴파일러에서 이름 → 번호 변환 (자동 추가)

```python
def resolve_switch_id(self, name: str) -> int:
    # SwitchTable은 불변 — allocate_switch()가 새 인스턴스 반환
    self._switch_table, sid = self._switch_table.allocate_switch(name)
    return sid
```

---

## R4. 맵 좌표 연결 불일치 (P1)

### 문제 설명

맵 이동 이벤트(transfer)가 지정하는 목적지 좌표가 실제 맵에서 벽 타일이면
캐릭터가 벽 안에 갇히거나 맵 이동 자체가 불가능해진다.

### 구체적 실패 시나리오

```
마을 → 던전 transfer 이벤트:
  to_map: 2 (어둠의 던전)
  to_x: 3
  to_y: 1   ← 던전 맵의 (3, 1)이 벽 타일인 경우

결과: 던전에 도착했는데 플레이어가 벽 안에 갇힘
     이동 불가 → 게임 진행 불가
```

### 완화 전략

#### 1차: E(타일 생성기)가 연결점 좌표를 출력

```python
# mapgen/__init__.py
def generate_map(spec: MapSpec, seed: int) -> tuple[list[int], MapConnectionInfo]:
    """타일 배열과 함께 연결점 정보를 반환한다."""
    if spec.map_type == "town":
        data = generate_town(spec, seed)
    elif spec.map_type in ("dungeon", "boss"):
        data = generate_dungeon(spec, seed)

    connection_info = extract_connection_info(spec, data)
    return data, connection_info
```

```python
# MapConnectionInfo 구조
@dataclass
class MapConnectionInfo:
    map_id: int
    spawn_point: tuple[int, int]          # 이 맵에 도착할 때 위치
    exit_points: dict[int, tuple[int, int]]  # to_map_id → 출구 타일 위치
```

#### 2차: 이벤트 기획자에게 실제 좌표 제공

```python
# event_planner.py 프롬프트에 포함
f"""
이 맵의 출구 좌표:
- 맵 2(어둠의 던전)로 가는 출구: x={exit_x}, y={exit_y}

맵 2에 도착할 때 플레이어 위치: x={dest_spawn_x}, y={dest_spawn_y}

transfer 이벤트를 배치할 때:
  x: {exit_x}, y: {exit_y}        # 출구 이벤트 위치
  to_map: 어둠의 던전
  to_x: {dest_spawn_x}
  to_y: {dest_spawn_y}
"""
```

#### 3차: 검증기에서 도착 좌표 검증

```python
def check_transfer_destinations(compiled_events: dict, map_tiles: dict) -> list[str]:
    errors = []
    for map_id, events in compiled_events.items():
        for event_data in events:
            for cmd in event_data.get("pages", [{}])[0].get("list", []):
                if cmd["code"] == 201:  # Transfer Player
                    dest_map = cmd["parameters"][1]
                    dest_x   = cmd["parameters"][2]
                    dest_y   = cmd["parameters"][3]
                    if dest_map in map_tiles:
                        tiles = map_tiles[dest_map]
                        map_w = get_map_width(dest_map)
                        if not is_walkable_raw(tiles, dest_x, dest_y, map_w):
                            errors.append(
                                f"[R4] Map{map_id} transfer → Map{dest_map} "
                                f"({dest_x},{dest_y})가 벽 타일"
                            )
    return errors
```

---

## R5. 컨텍스트 길이 초과 (P2)

### 문제 설명

이벤트 기획자(F) 실행 시 `game_spec + id_table + switch_table + map_spec` 을
모두 컨텍스트에 포함하면 토큰 한계를 초과할 수 있다.

### 토큰 추정 (게임 스펙 규모별)

| 게임 규모 | id_table 토큰 | 전체 컨텍스트 | 상태 |
|----------|-------------|-------------|------|
| 소규모 (에셋 30개) | ~300 | ~1,500 | 안전 |
| 중규모 (에셋 60개) | ~600 | ~1,800 | 안전 |
| 대규모 (에셋 100개) | ~1,000 | ~2,200 | 주의 |
| 초대규모 (에셋 200개) | ~2,000 | ~3,200 | 위험 |

Solar Pro 2 컨텍스트 한계: 32,768 토큰 → 1차 범위에서는 초과 가능성 낮음.

### 완화 전략

#### 1차: 관련 ID만 필터링

```python
def filter_id_table_for_map(id_table: IdTable, map_spec: MapSpec) -> dict:
    """
    이벤트 기획자가 이 맵에서 사용할 가능성이 있는 ID만 추출.
    맵 전체 id_table을 넘기지 않는다.
    """
    relevant = {}

    # 이 맵의 NPC가 상점이면 → items, weapons, armors ID 필요
    if any(l.landmark_type == "shop" for l in map_spec.landmarks):
        relevant["items"]   = id_table.items
        relevant["weapons"] = id_table.weapons
        relevant["armors"]  = id_table.armors

    # 이 맵에 전투 이벤트가 있으면 → enemies, troops ID 필요
    if map_spec.map_type in ("dungeon", "boss"):
        relevant["enemies"] = id_table.enemies
        relevant["troops"]  = id_table.troops

    # 맵 이동 → maps ID 항상 필요
    relevant["maps"] = id_table.maps

    return relevant
```

---

## R6. 생성 실패 복구 (P2)

### 문제 설명

긴 생성 파이프라인 중간에서 실패하면 처음부터 재실행 시 비용과 시간이 낭비된다.

### 복구 전략

#### 체크포인트 시스템

```python
# generation_workflow.py
async def run_with_checkpoint(state: GenerationState) -> GenerationState:
    phases = [
        ("spec",    game_designer),
        ("assets",  asset_generator),
        ("maps",    map_pipeline),      # D + E
        ("events",  event_pipeline),    # F + G
        ("final",   integrator),
        ("validate", generation_validator),
    ]

    for phase_name, phase_fn in phases:
        if phase_name in state.get("completed_phases", []):
            logger.info("Phase '%s' 이미 완료 → 건너뜀", phase_name)
            continue

        try:
            state = await phase_fn(state)
            state["completed_phases"] = [
                *state.get("completed_phases", []),
                phase_name,
            ]
            await save_checkpoint(state)   # S3 또는 DB에 저장
        except Exception as e:
            state["error_phase"]   = phase_name
            state["error_message"] = str(e)
            raise

    return state
```

#### 체크포인트 저장 위치

```
S3: s3://bucket/games/{game_id}/generations/{generation_id}/checkpoint.json

{
  "completed_phases": ["spec", "assets"],
  "game_spec": { ... },
  "id_table": { ... },
  "switch_table": { ... }
}
```

#### Phase별 재시도 비용

| Phase 실패 | 재시작 비용 | 재시작 시 LLM 호출 |
|-----------|-----------|-----------------|
| A. 기획자 | 높음 (전체 재시작) | ~11회 |
| C. 에셋 생성 | 낮음 (해당 에셋만) | 1~2회 |
| D. 맵 설계사 | 중간 | ~4회 |
| F. 이벤트 기획자 | 낮음 (해당 맵만) | 1회 |
| G. 컴파일러 | 없음 (LLM 없음) | 0회 |

---

## R7. 게임 밸런스 자동 검증 불가 (P2)

### 문제 설명

LLM이 생성한 수치가 실제로 플레이 가능한지 보장할 수 없다.

### 구체적 실패 시나리오

```
시나리오 1: 초반 즉사
  슬라임 ATK: 50 (생성된 값)
  주인공 HP:  100, DEF: 0
  → 슬라임 2번 맞으면 즉사
  → 레벨업 없는 1:1 전투에서 플레이 불가

시나리오 2: 보스가 너무 약함
  마왕 HP:  200
  주인공 ATK: 150, 스킬 데미지: 300
  → 1~2번 공격에 보스 사망
  → 클라이맥스 없는 허무한 엔딩

시나리오 3: 스킬 MP 소비 과다
  파이어볼 MP 소비: 80
  주인공 MaxMP: 50
  → 스킬을 영원히 사용 불가
```

### 완화 전략

#### 1차: LLM 프롬프트에 밸런스 공식 명시

```
적 스탯 생성 시 반드시 다음 기준을 지키세요:

플레이어 기준 HP: 150 (레벨 1)
                ATK: 15
                DEF: 5

적 티어별 기준:
  weak   → HP: 60~90,    ATK: 8~12    (2~3번 맞으면 위험)
  normal → HP: 120~180,  ATK: 12~18   (4~5번 위험)
  elite  → HP: 300~450,  ATK: 20~27
  boss   → HP: 2000~3000, ATK: 30~40

절대 초과 금지:
  weak 적 ATK > 플레이어 HP × 15% (22 이상 금지)
  boss HP < 플레이어 최대 데미지 × 10 (1500 미만 금지)
```

#### 2차: 검증기에서 수치 범위 검사

```python
def check_balance(assets: dict, spec: GameSpec) -> list[str]:
    warnings = []

    # 가장 약한 플레이어 기준
    actors  = [a for a in assets["Actors.json"] if a]
    player_hp  = min(a["params"][0] for a in actors)   # MHP
    player_atk = max(a["params"][2] for a in actors)   # ATK

    for enemy in assets["Enemies.json"]:
        if not enemy:
            continue
        enemy_atk = enemy["params"][2]
        enemy_hp  = enemy["params"][0]
        tier = enemy.get("meta", {}).get("tier", "normal")

        # 약한 적이 2번 공격에 플레이어를 죽이면 경고
        if tier == "weak" and enemy_atk * 2 >= player_hp:
            warnings.append(
                f"[R7] {enemy['name']} (weak) ATK={enemy_atk} 너무 높음 "
                f"(플레이어 HP {player_hp}의 50% 초과)"
            )

        # 보스가 너무 약으면 경고
        if tier == "boss" and enemy_hp < player_atk * 10:
            warnings.append(
                f"[R7] {enemy['name']} (boss) HP={enemy_hp} 너무 낮음 "
                f"(주인공 ATK {player_atk}의 10배 미만)"
            )

    # 스킬 MP 소비 검사
    min_mp = min(a["params"][1] for a in actors)  # MMP
    for skill in assets["Skills.json"]:
        if not skill:
            continue
        if skill.get("mpCost", 0) > min_mp:
            warnings.append(
                f"[R7] 스킬 '{skill['name']}' MP소비={skill['mpCost']} > "
                f"최소 MP={min_mp} (사용 불가)"
            )

    return warnings
```

---

## R8. 비용 (LLM 호출 수) (P3)

### 예상 LLM 호출 수 (Full Generation 1회)

```
A. 기획자:              1회
C. 에셋 생성 (병렬):   5~6회 (actors, classes, skills, items, enemies, troops)
D. 맵 설계사:           1회
F. 이벤트 기획자:       3회 (맵당 1회 × 3맵)
응답 생성:              1회
─────────────────
합계:                  11~12회
```

### 재생성 시 비용

| 재생성 범위 | LLM 호출 수 |
|-----------|-----------|
| spec (전체) | 11~12회 |
| assets만 | 5~6회 |
| maps만 | 4~5회 |
| events만 | 3회 |

### 완화 전략

- **부분 재생성 지원**: 사용자가 "맵만 다시 만들어줘" 요청 시 D+E+F+G만 재실행
- **결과 캐싱**: 동일 `user_input` + `seed`의 결과를 Redis에 24시간 캐싱
- **배치 처리**: 에셋 생성 시 1개 LLM 호출로 여러 에셋을 동시 생성 고려 (1~2개씩 묶음)

---

## R9. DSL 커버리지 한계 (P3)

### 1차(Phase 4)에서 지원하지 않는 이벤트 타입

```
미지원:
  ❌ 조건 중첩 (if 안에 if)
  ❌ 반복 루프 (특정 횟수만큼 실행)
  ❌ 병렬 이벤트 (화면 이동 없이 백그라운드 실행)
  ❌ 변수 연산 (점수, 카운터, 플래그 계산)
  ❌ 스크린 이펙트 (페이드인/아웃, 화면 흔들기)
  ❌ BGM/SE 변경
  ❌ 픽처 표시 (타이틀 화면, 엔딩 CG)
```

### 대응 방침

```
Phase 4 (1차 구현):
  ✅ npc (대화)
  ✅ transfer (맵 이동)
  ✅ chest (보물 상자)
  ✅ battle (전투)
  ✅ shop (상점)
  ✅ ending (엔딩 시퀀스)

Phase 5 (점진적 확장):
  → condition (단순 if/else) — Pydantic 모델·컴파일러 미구현
  → sign (안내판) — npc 타입으로 대체 가능
  → condition 중첩 지원
  → set_variable (변수 조작)
  → play_bgm / play_se
  → screen_effect

사용자에게 명시:
  1차에서는 "단순한 구조의 게임"으로 제한.
  복잡한 연출이나 분기가 많은 스토리는 Phase 5 이후 지원.
```

---

## R10. 타일 품질 (P3)

### 문제 설명

알고리즘으로 생성한 맵은 기능적으로는 동작하지만 디자인이 단조로울 수 있다.

### 완화 전략

- **시드(seed) 기반 랜덤**: 게임마다 다른 시드를 사용해서 맵 구조 차별화
- **멀티 템플릿**: 마을 레이아웃 3가지, 던전 레이아웃 3가지 → 게임마다 랜덤 선택
- **장식 레이어**: 알고리즘이 바닥/벽 배치 후 장식 타일(꽃, 횃불, 균열 등)을 랜덤으로 배치
- **장기 개선**: Phase 5에서 LLM이 맵 레이아웃 힌트를 제공하고 알고리즘이 따르는 방식 고려

---

## 모니터링 및 알림

### 주요 메트릭

```python
# 추적해야 할 지표
metrics = {
    "generation_success_rate":     "성공률 (목표 > 90%)",
    "avg_generation_time_seconds": "평균 생성 시간 (목표 < 60초)",
    "r1_id_error_rate":           "ID 참조 오류율 (목표 = 0%)",
    "r2_dsl_parse_failure_rate":  "DSL 파싱 실패율 (목표 < 5%)",
    "r2_retry_count":             "재시도 평균 횟수 (목표 < 1.2)",
    "r7_balance_warning_rate":    "밸런스 경고 발생률",
    "avg_llm_calls_per_game":     "게임당 LLM 호출 수",
}
```

### 알림 기준

| 상황 | 알림 레벨 |
|------|---------|
| 생성 실패율 > 20% | 즉시 알림 (Slack) |
| DSL 파싱 실패율 > 10% | 경고 (일 배치) |
| 평균 생성 시간 > 120초 | 경고 |
| ID 오류 발생 | 즉시 알림 (잠재적 시스템 버그) |

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- DSL 명세: `docs/The_world/dsl_specification.md`
- 맵 생성 알고리즘: `docs/The_world/map_generation.md`
- API 설계: `docs/The_world/generation_api.md`
