# Integrator 조립 가이드

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 목적

`integrator.py`(H 노드)는 LLM 없이 순수 알고리즘으로
모든 중간 결과물을 **완전한 RPG Maker MZ 프로젝트**로 조립한다.

이 문서는 각 파일을 어떻게 조립하는지 필드 수준으로 설명한다.
특히 `System.json`, `MapInfos.json`, `Troops.json`, `encounterList`는
다른 문서에서 다루지 않아 이곳에 집중 기술한다.

---

## 생성해야 하는 파일 목록

| 파일 | 소스 | 비고 |
|------|------|------|
| `Actors.json` | asset_generator 출력 | ensure_null_at_index_0 적용 |
| `Classes.json` | asset_generator 출력 | params 배열 검증 |
| `Skills.json` | asset_generator 출력 | |
| `Items.json` | asset_generator 출력 | |
| `Weapons.json` | asset_generator 출력 | |
| `Armors.json` | asset_generator 출력 | |
| `Enemies.json` | asset_generator 출력 | |
| `Troops.json` | **알고리즘** (LLM 없음) | enemies 목록 + 전투 배치 공식 |
| `System.json` | **알고리즘** (LLM 없음) | GameSpec + IdTable + SwitchTable |
| `MapInfos.json` | **알고리즘** (LLM 없음) | map_specs + id_table.maps |
| `Map001.json` | map_tiles + compiled_events | Phase 3+ |
| `Map002.json` | map_tiles + compiled_events | Phase 3+ |
| `Map00N.json` | map_tiles + compiled_events | Phase 3+ |
| `States.json` | **고정값** | `[null]` (상태이상 미사용) |
| `Animations.json` | **고정값** | `[null]` |
| `CommonEvents.json` | **고정값** | `[null]` |
| `Tilesets.json` | **고정값** | 3개 기본 타일셋 |

---

## 1. System.json 조립

System.json은 RPG Maker MZ 프로젝트에서 가장 중요한 설정 파일이다.
`startMapId`, `startX`, `startY`가 잘못되면 게임이 시작되지 않는다.

### 핵심 필드 조립 로직

```python
def build_system_json(
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    map_tiles: dict[int, list[int]],
    map_specs: list[MapSpec],
) -> dict:
    """System.json 완전 조립."""

    # 1. 시작 맵 찾기: type=="town"인 첫 번째 맵
    start_map_spec = next(
        (m for m in map_specs if m.map_type == "town"),
        map_specs[0],  # town이 없으면 첫 번째 맵
    )
    start_map_id = id_table.get_id("maps", start_map_spec.name)

    # 2. 시작 좌표: 스폰 포인트 (BFS로 walkable 타일 탐색)
    tiles = map_tiles[start_map_id]
    w, h = start_map_spec.width, start_map_spec.height
    spawn = calculate_spawn_point(tiles, w, h)
    start_x, start_y = spawn if spawn else (w // 2, h // 2)

    # 3. 스위치/변수 이름 배열 구성
    # SwitchTable: switches = {"boss_defeated": 1, "shop_unlocked": 2}
    # → switches 배열: [null, "boss_defeated", "shop_unlocked"]
    max_switch_id = max(switch_table.switches.values(), default=0)
    switches_arr: list[str | None] = [None] + [""] * max_switch_id
    for name, sid in switch_table.switches.items():
        switches_arr[sid] = name

    max_var_id = max(switch_table.variables.values(), default=0)
    variables_arr: list[str | None] = [None] + [""] * max_var_id
    for name, vid in switch_table.variables.items():
        variables_arr[vid] = name

    # 4. 초기 파티 멤버 (모든 액터)
    party_members = list(id_table.actors.values())

    # 5. 고정 타입 정의
    elements    = [None, "물리",  "화염",  "냉기",  "번개",  "성",    "암흑"]
    skill_types = [None, "마법",  "필살기"]
    weapon_types= [None, "단검",  "검",    "도끼",  "지팡이", "활"]
    armor_types = [None, "일반방어구", "마법방어구", "장신구"]
    equip_types = [None, "무기",  "방패",  "투구",  "갑옷",  "장신구"]

    return {
        "gameTitle": game_spec.title,
        "locale": "ko_KR",
        "currencyUnit": "G",
        "startMapId": start_map_id,
        "startX": start_x,
        "startY": start_y,
        "partyMembers": party_members,
        "switches": switches_arr,
        "variables": variables_arr,
        "elements": elements,
        "skillTypes": skill_types,
        "weaponTypes": weapon_types,
        "armorTypes": armor_types,
        "equipTypes": equip_types,
        "magicSkills": [1],  # skillType 1 = 마법
        "menuCommands": [True, True, True, True, True, True],
        "optDisplayTp": False,
        "optDrawTitle": True,
        "optExtraExp": False,
        "optFloorDeath": False,
        "optFollowers": True,
        "optSideView": False,
        "optSlipDeath": False,
        "optTransparent": False,
        "versionId": 1,
        "editMapId": start_map_id,
        "battleBgm":  _audio("Battle1"),
        "defeatMe":   _audio("Defeat1"),
        "gameoverMe": _audio("Gameover1"),
        "titleBgm":   _audio("Theme6"),
        "victoryMe":  _audio("Victory1"),
        "title1Name": "",
        "title2Name": "",
        "battleback1Name": "",
        "battleback2Name": "",
        "battlerName": "",
        "battlerHue": 0,
        "sounds": _default_sounds(),
        "attackMotions": _default_attack_motions(),
        "terms": _default_terms(),
        "airship": _default_vehicle(),
        "boat":    _default_vehicle(),
        "ship":    _default_vehicle(),
        "testBattlers": [],
        "testTroopId": 1,
        "windowTone": [0, 0, 0, 0],
    }

def _audio(name: str = "", volume: int = 90, pitch: int = 100) -> dict:
    return {"name": name, "volume": volume, "pitch": pitch, "pan": 0}

def _default_vehicle() -> dict:
    return {
        "bgm": _audio(),
        "characterIndex": 0,
        "characterName": "",
        "startMapId": 0,
        "startX": 0,
        "startY": 0,
    }
```

### 시작 좌표 결정 — R16 방지

**R16 리스크**: `startX`, `startY`가 벽 타일을 가리키면 플레이어가 즉시 갇힌다.

```python
from collections import deque

WALKABLE_TILE_IDS = {0x0000, 0x0001, 0x0002, 0x0003, 0x0004}  # tile_constants.py 참조

def calculate_spawn_point(
    tiles: list[int],
    width: int,
    height: int,
    preferred_region: str = "center",
) -> tuple[int, int] | None:
    """
    BFS로 첫 번째 walkable 타일 탐색.
    preferred_region="center": 맵 중앙 근처 우선
    preferred_region="top": 맵 상단 우선 (던전 입구)
    """
    # 레이어 0만 사용 (tiles[:width*height])
    layer0 = tiles[:width * height]

    def is_walkable(x: int, y: int) -> bool:
        if x < 0 or x >= width or y < 0 or y >= height:
            return False
        return layer0[y * width + x] in WALKABLE_TILE_IDS

    # 시작점: 선호 영역에 따라
    if preferred_region == "center":
        starts = [(width // 2, height // 2)]
    else:
        starts = [(x, 0) for x in range(width // 3, 2 * width // 3)]

    # BFS로 가장 가까운 walkable 타일 탐색
    visited = set()
    queue: deque[tuple[int, int]] = deque()
    for s in starts:
        if is_walkable(*s):
            return s  # 즉시 반환
        queue.append(s)
        visited.add(s)

    while queue:
        x, y = queue.popleft()
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited and 0 <= nx < width and 0 <= ny < height:
                visited.add((nx, ny))
                if is_walkable(nx, ny):
                    return (nx, ny)
                queue.append((nx, ny))

    return None  # 모든 타일이 벽 (있어서는 안 됨)
```

> **검증**: `calculate_spawn_point()`가 `None`을 반환하면
> `generation_validator`에서 오류로 처리한다.

---

## 2. MapInfos.json 조립

**MapInfos.json**은 RPG Maker MZ 에디터에서 왼쪽 맵 트리를 구성하는 파일이다.
이 파일이 없거나 맵 ID가 불일치하면 에디터에서 맵을 열 수 없다.

> **주의**: RPG Maker MZ는 MapInfos.json이 없어도 게임 **실행**은 가능하지만,
> 에디터에서 맵을 열 수 없다. 호환성을 위해 항상 생성한다.

### 구조

```json
{
  "1": {"id": 1, "expanded": true,  "name": "출발 마을", "order": 1, "parentId": 0, "scrollX": 0, "scrollY": 0},
  "2": {"id": 2, "expanded": false, "name": "어둠의 숲",  "order": 2, "parentId": 0, "scrollX": 0, "scrollY": 0},
  "3": {"id": 3, "expanded": false, "name": "드래곤 소굴","order": 3, "parentId": 0, "scrollX": 0, "scrollY": 0}
}
```

MapInfos.json은 **배열이 아닌 딕셔너리**임에 주의. 키는 문자열 정수.

### 조립 함수

```python
def build_map_infos(
    map_specs: list[MapSpec],
    id_table: IdTable,
) -> dict[str, dict]:
    """MapInfos.json 딕셔너리 조립."""
    result = {}
    for order, spec in enumerate(map_specs, start=1):
        map_id = id_table.get_id("maps", spec.name)
        result[str(map_id)] = {
            "id": map_id,
            "expanded": order == 1,  # 첫 번째 맵만 펼침
            "name": spec.name,
            "order": order,
            "parentId": 0,  # 모두 최상위 (단순 구조)
            "scrollX": 0,
            "scrollY": 0,
        }
    return result
```

---

## 3. Troops.json 조립 — 알고리즘

`Troops.json`은 전투 그룹을 정의한다. 에셋 생성(C 노드)에서 enemies 목록을 받아
**LLM 없이 알고리즘으로** troop을 구성한다.

### Troop 배치 규칙

```python
# 전투 화면 크기: 816 × 624픽셀
# 적 스프라이트 표준 크기: ~96×96픽셀

BATTLE_POSITIONS = {
    1: [(408, 312)],                                   # 단독 1마리: 중앙
    2: [(280, 312), (536, 312)],                       # 2마리: 좌우 대칭
    3: [(180, 260), (408, 360), (636, 260)],           # 3마리: 삼각형
    4: [(200, 240), (400, 240), (200, 380), (400, 380)], # 4마리: 2×2
}

def generate_troops(enemies: list[dict], id_table: IdTable) -> list[dict | None]:
    """
    enemies 목록에서 Troops.json 생성.

    전략:
    - weak/normal 적: 단독 + 2마리 + 3마리 troop 생성
    - elite 적: 단독 troop만
    - boss 적: 단독 troop, 더 큰 화면 중앙 배치
    """
    troops: list[dict | None] = [None]  # index-0 null 규칙

    for enemy in enemies:
        enemy_id = id_table.get_id("enemies", enemy["name"])
        tier = _detect_tier(enemy)

        if tier == "boss":
            # 보스: 단독, 중앙 배치
            troops.append(_make_troop(
                troop_id=len(troops),
                name=f"{enemy['name']}",
                members=[_make_member(enemy_id, 408, 312)],
            ))
        elif tier == "elite":
            # 엘리트: 단독
            troops.append(_make_troop(
                troop_id=len(troops),
                name=f"{enemy['name']} × 1",
                members=[_make_member(enemy_id, 408, 312)],
            ))
        else:
            # weak/normal: 1마리, 2마리, 3마리 변형 생성
            for count in [1, 2, 3]:
                if count > 3:
                    break
                positions = BATTLE_POSITIONS[count]
                troops.append(_make_troop(
                    troop_id=len(troops),
                    name=f"{enemy['name']} × {count}",
                    members=[_make_member(enemy_id, x, y) for x, y in positions],
                ))

    return troops

def _detect_tier(enemy: dict) -> str:
    """HP 기준으로 적 티어 추정 (tier 필드 없을 경우)."""
    hp = enemy["params"][0] if "params" in enemy else 0
    if hp >= 2000: return "boss"
    if hp >= 500:  return "elite"
    if hp >= 200:  return "normal"
    return "weak"

def _make_troop(troop_id: int, name: str, members: list[dict]) -> dict:
    return {
        "id": troop_id,
        "name": name,
        "members": members,
        "pages": [_default_troop_page()],
    }

def _make_member(enemy_id: int, x: int, y: int) -> dict:
    return {"enemyId": enemy_id, "hidden": False, "x": x, "y": y}

def _default_troop_page() -> dict:
    """조건 없는 빈 전투 이벤트 페이지."""
    return {
        "conditions": {
            "turnEnding": False, "turnValid": False, "turnA": 0, "turnB": 0,
            "enemyValid": False, "enemyIndex": 0, "enemyHp": 50,
            "actorValid": False, "actorId": 1, "actorHp": 50,
            "switchValid": False, "switchId": 1,
        },
        "list": [{"code": 0, "indent": 0, "parameters": []}],
        "span": 0,
    }
```

### IdTable troop 병합

`generate_troops()` 실행 후 `id_table.troops`를 업데이트해야 한다:
```python
def _update_troop_ids(troops: list[dict | None], id_table: IdTable) -> IdTable:
    """생성된 troop 이름 → ID 매핑을 id_table에 병합."""
    troop_ids = {
        t["name"]: t["id"]
        for t in troops if t is not None
    }
    return id_table.model_copy(update={"troops": troop_ids})
```

---

## 4. encounterList 설정 — 랜덤 인카운터

`encounterList`는 Map*.json 내부에 있으며, 맵을 걷다가 무작위로 발생하는 전투를 설정한다.

### 맵 타입별 정책

| 맵 타입 | encounterList | encounterStep | 이유 |
|---------|--------------|---------------|------|
| `town`  | `[]` (비어있음) | 30 | 마을에서는 랜덤 전투 없음 |
| `field` | weak/normal 트루프 | 25 | 야외 필드 |
| `dungeon` | normal/elite 트루프 | 20 | 던전은 더 빈번 |
| `boss`  | `[]` (비어있음) | 30 | 보스 전투는 이벤트로만 |

### 조립 함수

```python
def build_encounter_list(
    map_spec: MapSpec,
    troops: list[dict | None],
    id_table: IdTable,
) -> tuple[list[dict], int]:
    """
    encounterList와 encounterStep을 반환.
    맵 타입에 따라 적절한 트루프를 선택한다.
    """
    if map_spec.map_type in ("town", "boss"):
        return [], 30

    step = 20 if map_spec.map_type == "dungeon" else 25

    # 해당 맵에 등장해야 하는 적 이름 목록 (MapSpec.description에서 추출)
    # 더 정확하게는 game_spec에서 location 정보를 가져와야 하지만,
    # Phase 3에서는 단순화: 맵 타입에 맞는 티어의 트루프를 선택
    target_tiers = {"dungeon": ("normal", "elite"), "field": ("weak", "normal")}
    allowed_tiers = target_tiers.get(map_spec.map_type, ("weak",))

    encounters = []
    for troop in troops:
        if troop is None:
            continue
        # 트루프 이름에서 적 티어 추정 (단순화)
        tier = _estimate_troop_tier(troop, troops)
        if tier in allowed_tiers:
            encounters.append({
                "troopId": troop["id"],
                "weight": 10,  # 모두 동일 가중치 (단순화)
                "regionSet": [],  # 전체 맵 (특정 리전 없음)
            })

    return encounters, step

def _estimate_troop_tier(troop: dict, all_troops: list[dict | None]) -> str:
    """트루프 이름에서 "× N" 패턴으로 수량 추정 → 티어 결정."""
    name = troop.get("name", "")
    if "× 3" in name:
        return "normal"
    if "× 2" in name:
        return "normal"
    if "× 1" in name:
        # 단독이면 멤버 수로 HP 체크 불가 → weak으로 처리
        return "weak"
    return "elite"  # 이름에 ×가 없으면 elite/boss
```

---

## 5. Map*.json 조립

```python
def build_map_json(
    map_spec: MapSpec,
    tiles: list[int],
    compiled_events: list[dict],
    tileset_id: int,
    troops: list[dict | None],
    id_table: IdTable,
) -> dict:
    """MapFile 완전 조립."""
    encounter_list, encounter_step = build_encounter_list(map_spec, troops, id_table)

    # events 배열: index-0은 null, 이후 이벤트가 순서대로
    events_arr: list[dict | None] = [None]
    for i, event in enumerate(compiled_events, start=1):
        event_with_id = {**event, "id": i}  # ID는 통합기가 부여
        events_arr.append(event_with_id)

    return {
        "autoplayBgm": True,
        "autoplayBgs": False,
        "battleback1Name": _map_battle_bg1(map_spec.map_type),
        "battleback2Name": _map_battle_bg2(map_spec.map_type),
        "bgm": _map_bgm(map_spec.map_type),
        "bgs": {"name": "", "volume": 0, "pitch": 100, "pan": 0},
        "disableDashing": False,
        "displayName": map_spec.name,
        "encounterList": encounter_list,
        "encounterStep": encounter_step,
        "height": map_spec.height,
        "width": map_spec.width,
        "note": "",
        "parallaxLoopX": False,
        "parallaxLoopY": False,
        "parallaxName": "",
        "parallaxShow": True,
        "parallaxSx": 0,
        "parallaxSy": 0,
        "scrollType": 0,
        "specifyBattleback": bool(map_spec.map_type in ("dungeon", "boss")),
        "tilesetId": tileset_id,
        "data": tiles,
        "events": events_arr,
    }

# BGM 매핑 (기본 RPG Maker MZ 동봉 음원 사용)
_BGM_BY_TYPE = {
    "town":    "Town1",
    "field":   "Field1",
    "dungeon": "Dungeon1",
    "boss":    "Boss1",
}
_BATTLEBACK1_BY_TYPE = {
    "town":    "Village",
    "field":   "GrassMaze",
    "dungeon": "DungeonA4",
    "boss":    "DungeonA4",
}
_BATTLEBACK2_BY_TYPE = {
    "town":    "Village2",
    "field":   "Sky",
    "dungeon": "DungeonB",
    "boss":    "DungeonB",
}

def _map_bgm(map_type: str) -> dict:
    name = _BGM_BY_TYPE.get(map_type, "Town1")
    return {"name": name, "volume": 90, "pitch": 100, "pan": 0}

def _map_battle_bg1(map_type: str) -> str:
    return _BATTLEBACK1_BY_TYPE.get(map_type, "Village")

def _map_battle_bg2(map_type: str) -> str:
    return _BATTLEBACK2_BY_TYPE.get(map_type, "Village2")
```

---

## 6. 고정값 파일

다음 파일들은 항상 동일한 최소값으로 생성한다:

```python
FIXED_FILES = {
    "States.json":       [None],
    "Animations.json":   [None],
    "CommonEvents.json": [None],
    "Tilesets.json":     _build_default_tilesets(),
}

def _build_default_tilesets() -> list[dict | None]:
    """
    기본 3개 타일셋:
    - ID 1: 마을 (TileA1~A5, B, C)
    - ID 2: 던전
    - ID 3: 필드 (미사용, 예비)
    """
    return [
        None,
        _tileset(1, "마을", "World_A1", "World_A2", "World_A3", "World_A4", "World_A5",
                 "World_B", "World_C", "World_D", "World_E"),
        _tileset(2, "던전", "Dungeon_A1", "Dungeon_A2", "Dungeon_A3", "Dungeon_A4", "Dungeon_A5",
                 "Dungeon_B", "Dungeon_C", "World_D", "World_E"),
        _tileset(3, "필드",  "World_A1",   "World_A2",   "World_A3",   "World_A4",   "World_A5",
                 "Inside_B", "Inside_C", "World_D", "World_E"),
    ]

def _tileset(tid: int, name: str, *tile_names: str) -> dict:
    return {
        "id": tid,
        "flags": [0] * 8192,  # 통행 가능 플래그 (0=양방향 통행)
        "mode": 1,
        "name": name,
        "tilesetNames": list(tile_names) + [""] * (9 - len(tile_names)),
    }
```

> **주의**: `flags` 배열은 타일별 통행 방향을 결정한다.
> Full Generation에서는 모두 0(양방향)으로 설정하고,
> 실제 통행 가능 여부는 타일 ID로만 제어한다.

---

## 7. 통합 흐름

```python
async def run_integrator(state: GenerationState) -> dict:
    spec      = state["game_spec"]
    id_table  = state["id_table"]
    sw_table  = state["switch_table"]
    assets    = state["generated_assets"]
    map_specs = state.get("map_specs", [])
    map_tiles = state.get("map_tiles", {})
    compiled  = state.get("compiled_events", {})

    final: dict[str, Any] = {}

    # 1. 에셋 파일 (index-0 null 규칙 적용)
    for asset_type, data in assets.items():
        filename = ASSET_TO_FILENAME[asset_type]
        final[filename] = ensure_null_at_index_0(data)

    # 2. Troops.json (알고리즘 생성)
    enemies = assets.get("enemies", [])
    troops  = generate_troops(enemies, id_table)
    id_table = _update_troop_ids(troops, id_table)
    final["Troops.json"] = troops

    # 3. System.json
    final["System.json"] = build_system_json(
        spec, id_table, sw_table, map_tiles, map_specs
    )

    # 4. MapInfos.json
    if map_specs:
        final["MapInfos.json"] = build_map_infos(map_specs, id_table)

    # 5. Map*.json (Phase 3+)
    for ms in map_specs:
        mid = id_table.get_id("maps", ms.name)
        filename = f"Map{mid:03d}.json"
        final[filename] = build_map_json(
            map_spec=ms,
            tiles=map_tiles[mid],
            compiled_events=compiled.get(mid, []),
            tileset_id=MAP_TYPE_TO_TILESET[ms.type],
            troops=troops,
            id_table=id_table,
        )

    # 6. 고정값 파일
    final.update(FIXED_FILES)

    return {"final_project": final, "id_table": id_table}
```

---

## 8. 관련 리스크

### R16 — startMapId/startX/startY 오류

**발생 경로**: `calculate_spawn_point()`가 None 반환 (모든 타일이 벽).
이 경우 `build_system_json()`이 `(width//2, height//2)` 폴백 사용.
폴백 좌표가 벽이면 게임 시작 시 플레이어 이동 불가.

**방지**:
```python
# generation_validator.py에 추가
def check_start_position(project: dict, map_tiles: dict) -> list[str]:
    system = project.get("System.json", {})
    mid  = system.get("startMapId", 0)
    sx   = system.get("startX", 0)
    sy   = system.get("startY", 0)
    if mid not in map_tiles:
        return [f"startMapId={mid} 타일 데이터 없음"]
    tiles = map_tiles[mid]
    map_file = project.get(f"Map{mid:03d}.json", {})
    w = map_file.get("width", 1)
    idx = sy * w + sx
    if idx < len(tiles) and tiles[idx] not in WALKABLE_TILE_IDS:
        return [f"시작 좌표 ({sx},{sy})가 벽 타일임 (tile={hex(tiles[idx])})"]
    return []
```

### R17 — Troop 전투 화면 좌표 범위 초과

**발생 경로**: `BATTLE_POSITIONS` 값이 816×624 범위 초과 시 전투 화면에서 적이 안 보임.

**방지**: 배치 좌표 상수를 항상 `0 ≤ x ≤ 816`, `0 ≤ y ≤ 624` 범위 내로 고정.
`_make_member()` 내부에서 범위 체크:
```python
def _make_member(enemy_id: int, x: int, y: int) -> dict:
    assert 0 <= x <= 816, f"troop member x={x} out of range"
    assert 0 <= y <= 624, f"troop member y={y} out of range"
    return {"enemyId": enemy_id, "hidden": False, "x": x, "y": y}
```

### R18 — MapInfos.json 맵 ID 불일치

**발생 경로**: MapInfos.json의 키가 Map*.json 파일명의 숫자와 다를 경우.
예: `MapInfos.json["2"]`인데 파일이 `Map002.json`이 아닌 `Map2.json`으로 저장됨.

**방지**: 파일명 포맷을 항상 `f"Map{mid:03d}.json"` (3자리 zero-padding)으로 고정.
MapInfos.json 키도 `str(map_id)`로 고정.

```python
def check_map_id_consistency(project: dict) -> list[str]:
    """MapInfos.json의 ID와 실제 Map*.json 파일이 1:1 대응하는지 검증."""
    errors = []
    infos = project.get("MapInfos.json", {})
    for map_id_str, info in infos.items():
        expected_file = f"Map{int(map_id_str):03d}.json"
        if expected_file not in project:
            errors.append(f"MapInfos.json[{map_id_str}] → {expected_file} 파일 없음")
    return errors
```

---

## 9. Phase 2에서의 간략 조립

Phase 2(에셋만)에서는 맵이 없으므로 다음만 생성:

```python
# Phase 2 integrator (맵 없음)
final["System.json"]  = build_system_json_assets_only(spec, id_table, sw_table)
final["MapInfos.json"] = {}  # 빈 딕셔너리
final["Map001.json"]  = _build_placeholder_map()  # 검은 화면 (시작 맵)

def _build_placeholder_map() -> dict:
    """Phase 2용 빈 맵 (30×30, 전부 벽)."""
    w, h = 30, 30
    return {
        "autoplayBgm": False, "autoplayBgs": False,
        "battleback1Name": "", "battleback2Name": "",
        "bgm": _audio(), "bgs": _audio(),
        "disableDashing": False, "displayName": "???",
        "encounterList": [], "encounterStep": 30,
        "height": h, "width": w,
        "note": "", "parallaxLoopX": False, "parallaxLoopY": False,
        "parallaxName": "", "parallaxShow": True, "parallaxSx": 0, "parallaxSy": 0,
        "scrollType": 0, "specifyBattleback": False,
        "tilesetId": 1,
        "data": [0] * (w * h * 6),
        "events": [None],
    }
```
