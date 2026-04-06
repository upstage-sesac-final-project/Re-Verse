# RPG Maker MZ 기본 동봉 리소스 레퍼런스

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 목적

Full Generation에서 LLM이 `faceName`, `characterName`, `battlerName`,
BGM/ME/SE 파일명을 생성할 때 **반드시 이 목록에서만** 선택해야 한다.
존재하지 않는 파일명을 생성하면 게임에서 빈 스프라이트/무음이 된다.

이 목록은 RPG Maker MZ 정식 설치 시 기본 동봉되는 파일 기준이다 (RTP).

---

## R19. 존재하지 않는 리소스 파일명 (P1)

| 증상 | 원인 | 영향 |
|------|------|------|
| 액터 스프라이트 안 보임 | `characterName` 파일 없음 | 게임 내 캐릭터 투명 |
| 얼굴 이미지 안 보임 | `faceName` 파일 없음 | 대화창 얼굴 표시 안 됨 |
| 전투 스프라이트 안 보임 | `battlerName` 파일 없음 | SV 전투에서 캐릭터 없음 |
| BGM 재생 안 됨 | 파일명 오타 | 무음 |

**방지**: `asset_generator_prompt.py`에 아래 유효 목록을 직접 주입.
`generation_validator.check_resource_filenames()`로 최종 검증.

---

## 1. 캐릭터 스프라이트 (`characterName` + `characterIndex`)

`img/characters/` 디렉터리의 파일.
각 파일은 **4행 × 3열 = 12 캐릭터** (index 0~11 → 0~7까지만 허용).

### 주인공/NPC용

| 파일명 | 설명 | index 범위 |
|--------|------|-----------|
| `Actor1` | 젊은 남성 캐릭터 4명 × 남성 변형 4명 | 0~7 |
| `Actor2` | 여성 캐릭터 4명 × 여성 변형 4명 | 0~7 |
| `Actor3` | 기사/마법사 스타일 | 0~7 |
| `Actor4` | 성직자/궁수 스타일 | 0~7 |
| `Actor5` | 노인/어린이 스타일 | 0~7 |
| `Actor6` | 이국적 스타일 | 0~7 |
| `Actor7` | 특수 캐릭터 | 0~7 |
| `Actor8` | 특수 캐릭터 | 0~7 |

### 마을 NPC용

| 파일명 | 설명 | index 범위 |
|--------|------|-----------|
| `People1` | 농부/상인/마을 주민 | 0~7 |
| `People2` | 다양한 직업 주민 | 0~7 |
| `People3` | 어린이/노인 | 0~7 |
| `People4` | 귀족/성직자 | 0~7 |

### 몬스터 맵 스프라이트 (이벤트용)

| 파일명 | 설명 |
|--------|------|
| `Monster` | 슬라임/고블린 등 |
| `Evil` | 악당/마왕 캐릭터 |

### 특수

| 파일명 | 설명 |
|--------|------|
| `!Chest` | 보물상자 |
| `!Door` | 문 |
| `!Crystal` | 크리스탈 |
| `!Barrel` | 배럴 |
| `!Flame` | 불꽃 |

> `!` 접두사 파일은 `characterIndex: 0`만 유효.

---

## 2. 얼굴 이미지 (`faceName` + `faceIndex`)

`img/faces/` 디렉터리. 각 파일은 **4행 × 2열 = 8 얼굴** (index 0~7).

| 파일명 | 설명 | 권장 사용 |
|--------|------|---------|
| `Actor1` | 남성 주인공 스타일 | 플레이어 캐릭터 |
| `Actor2` | 여성 주인공 스타일 | 플레이어 캐릭터 |
| `Actor3` | 전사/기사 스타일 | 전투 캐릭터 |
| `Actor4` | 마법사/성직자 스타일 | 마법사 캐릭터 |
| `Actor5` | 노인/어린이 | NPC |
| `Actor6` | 이국적 | NPC |
| `Actor7` | 특수 | NPC |
| `Actor8` | 특수 | NPC |
| `People1` | 마을 주민 | NPC |
| `People2` | 다양한 주민 | NPC |
| `People3` | 어린이/노인 | NPC |
| `People4` | 귀족/성직자 | NPC |
| `Evil` | 악당 얼굴 | 보스/적 NPC |

---

## 3. SV 전투 스프라이트 (`battlerName`)

`img/sv_actors/` 디렉터리. SV(사이드뷰) 전투용.
형식: `"Actor1_1"` — 파일명 `Actor1`, 번호 `1`.

| 파일명 | 설명 |
|--------|------|
| `Actor1_1` | 남성 검사 |
| `Actor1_2` | 남성 마법사 |
| `Actor1_3` | 남성 성직자 |
| `Actor1_4` | 남성 궁수 |
| `Actor1_5` ~ `Actor1_8` | 남성 기타 |
| `Actor2_1` | 여성 검사 |
| `Actor2_2` | 여성 마법사 |
| `Actor2_3` | 여성 성직자 |
| `Actor2_4` | 여성 궁수 |
| `Actor2_5` ~ `Actor2_8` | 여성 기타 |

> Full Generation에서는 `optSideView: false` (System.json)이므로
> `battlerName`은 전투 테스트용으로만 사용된다. 빈 문자열도 허용.

---

## 4. BGM 파일 (`img/audio/bgm/`)

맵 타입별 권장 BGM:

| 파일명 | 맞는 맵 타입 | 분위기 |
|--------|------------|--------|
| `Town1` | town | 평화로운 마을 |
| `Town2` | town | 활기찬 마을 |
| `Town3` | town | 조용한 마을 |
| `Field1` | field | 모험적인 필드 |
| `Field2` | field | 신비로운 필드 |
| `Dungeon1` | dungeon | 어두운 던전 |
| `Dungeon2` | dungeon | 으스스한 던전 |
| `Dungeon3` | dungeon | 긴박한 던전 |
| `Boss1` | boss | 긴박한 보스전 분위기 (맵 BGM) |
| `Battle1` | (전투 BGM) | 일반 전투 |
| `Battle2` | (전투 BGM) | 격렬한 전투 |
| `Battle3` | (전투 BGM) | 빠른 전투 |
| `Boss1` | (전투 BGM) | 보스 전투 |
| `Boss2` | (전투 BGM) | 긴박한 보스 |
| `Theme1`~`Theme7` | (타이틀) | 타이틀 화면 |

---

## 5. ME (음악 효과) 파일

| 파일명 | 사용 |
|--------|------|
| `Victory1` | 전투 승리 |
| `Defeat1` | 전투 패배 |
| `Gameover1` | 게임오버 |
| `Item1` | 아이템 획득 |

---

## 6. 전투 배경 (`battleback1Name`, `battleback2Name`)

맵 타입별 권장 전투 배경:

| 맵 타입 | battleback1Name | battleback2Name |
|---------|----------------|----------------|
| `town` | `Village` | `Village2` |
| `field` | `GrassMaze` | `Sky` |
| `dungeon` | `DungeonA4` | `DungeonB` |
| `boss` | `DungeonA4` | `DungeonB` |

---

## 7. 맵 크기 표준

`map_designer.py`에서 LLM에게 MapSpec을 요청할 때 width/height를 미리 정해 주입한다.
LLM이 임의의 크기를 생성하면 타일 생성기와 불일치 발생.

| 맵 타입 | 권장 크기 (width × height) | 이유 |
|---------|--------------------------|------|
| `town` | 30 × 30 | NPC 8개, 건물 4개 배치 가능 |
| `field` | 40 × 30 | 넓은 이동 공간 |
| `dungeon` | 40 × 30 | BSP 분할 최적 크기 (최소 6×6 방 4~6개) |
| `boss` | 20 × 20 | 작은 보스 방 |

이 값은 `map_designer_prompt.py`에 **하드코딩**하여 LLM이 변경할 수 없게 한다:

```python
MAP_SIZE_BY_TYPE: dict[str, tuple[int, int]] = {
    "town":    (30, 30),
    "field":   (40, 30),
    "dungeon": (40, 30),
    "boss":    (20, 20),
}

def build_map_designer_prompt(spec: GameSpec, id_table: IdTable) -> list[BaseMessage]:
    # MapSpec에 width/height를 미리 명시
    map_size_info = "\n".join(
        f"- {m.name} ({m.type}): width={MAP_SIZE_BY_TYPE[m.type][0]}, height={MAP_SIZE_BY_TYPE[m.type][1]}"
        for m in spec.maps
    )
    system = f"""...
각 맵의 크기는 다음으로 고정됩니다:
{map_size_info}
MapSpec.width와 MapSpec.height는 위 값을 정확히 사용하세요.
..."""
    ...
```

그리고 MapSpec 모델에 width/height를 추가:

```python
class MapSpec(BaseModel):
    name: str
    type: Literal["town", "dungeon", "boss", "field"]
    description: str
    connects_to: list[str]
    width: int = 30    # map_designer가 채움 (고정값)
    height: int = 30   # map_designer가 채움 (고정값)
    landmarks: list[str] = []  # NPC 위치 힌트 (선택)
```

---

## 8. 프롬프트 주입 예시

`asset_generator_prompt.py`에서 Actor 생성 시:

```python
ACTOR_RESOURCE_RULES = """
## 이미지 파일명 규칙 (반드시 아래 목록에서만 선택)

characterName 허용값: "Actor1", "Actor2", "Actor3", "Actor4",
                      "Actor5", "Actor6", "Actor7", "Actor8"
characterIndex: 0~7 정수

faceName 허용값: "Actor1", "Actor2", "Actor3", "Actor4",
                 "Actor5", "Actor6", "Actor7", "Actor8"
faceIndex: 0~7 정수

battlerName: "Actor1_1" ~ "Actor1_8", "Actor2_1" ~ "Actor2_8"
             (형식: "Actor{N}_{M}" N=1~2, M=1~8)
             또는 "" (빈 문자열, SV 전투 미사용)

## 할당 가이드
- 주인공 (role="주인공"): characterName="Actor1" 또는 "Actor2"
- 서포터/딜러:           characterName="Actor3" ~ "Actor4"
- 탱커:                 characterName="Actor3"
- 같은 파일을 여러 캐릭터에 사용 가능 (characterIndex로 구분)
"""
```

---

## 9. 리소스 파일명 검증기

```python
VALID_CHARACTER_NAMES = {
    "Actor1", "Actor2", "Actor3", "Actor4",
    "Actor5", "Actor6", "Actor7", "Actor8",
    "People1", "People2", "People3", "People4",
    "Monster", "Evil",
    "!Chest", "!Door", "!Crystal", "!Barrel", "!Flame",
}

VALID_FACE_NAMES = {
    "Actor1", "Actor2", "Actor3", "Actor4",
    "Actor5", "Actor6", "Actor7", "Actor8",
    "People1", "People2", "People3", "People4", "Evil",
}

VALID_BGM_NAMES = {
    "Town1", "Town2", "Town3",
    "Field1", "Field2",
    "Dungeon1", "Dungeon2", "Dungeon3",
    "Battle1", "Battle2", "Battle3",
    "Boss1", "Boss2",
    "Theme1", "Theme2", "Theme3", "Theme4", "Theme5", "Theme6", "Theme7",
    "",  # 빈 문자열 허용 (무음)
}

def check_resource_filenames(project: dict) -> list[str]:
    """생성된 JSON에서 잘못된 리소스 파일명 검출."""
    errors = []
    for actor in project.get("Actors.json", [])[1:]:
        if actor is None: continue
        if actor.get("characterName") not in VALID_CHARACTER_NAMES:
            errors.append(
                f"Actor '{actor['name']}' characterName='{actor.get('characterName')}' 유효하지 않음"
            )
        if actor.get("faceName") not in VALID_FACE_NAMES:
            errors.append(
                f"Actor '{actor['name']}' faceName='{actor.get('faceName')}' 유효하지 않음"
            )

    system = project.get("System.json", {})
    if system.get("battleBgm", {}).get("name") not in VALID_BGM_NAMES:
        errors.append(f"battleBgm '{system.get('battleBgm')}' 유효하지 않음")

    return errors
```

이 검증은 `generation_validator.run_generation_validator()`에 포함한다.
