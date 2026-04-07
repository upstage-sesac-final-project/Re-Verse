# RPG Maker MZ 기본 동봉 리소스 레퍼런스

> 기준: `storage/games/base_game/img/` 실제 파일 전수 확인 (이미지 직접 열람)
> 최초 작성: 2026-04-06 / 최종 수정: 2026-04-07
> 전체 매핑 상세: `docs/The_world/image_asset_mapping.md` 참조

---

## 목적

Full Generation에서 LLM이 `faceName`, `characterName`, `battlerName`,
`battleback1Name`, `battleback2Name` 파일명을 생성할 때 **반드시 이 목록에서만** 선택해야 한다.
존재하지 않는 파일명을 생성하면 게임에서 빈 스프라이트/검정 화면이 된다.

---

## R19. 존재하지 않는 리소스 파일명 (P1)

| 증상 | 원인 | 영향 |
|------|------|------|
| 액터 스프라이트 안 보임 | `characterName` 파일 없음 | 투명 캐릭터 |
| 얼굴 이미지 안 보임 | `faceName` 파일 없음 | 대화창 빈칸 |
| 전투 스프라이트 안 보임 | `battlerName` 파일 없음 | SV 전투에서 캐릭터 없음 |
| 전투 배경 검정 | `battleback1Name` / `battleback2Name` 파일 없음 | 배경 없음 |

**방지**: `asset_generator_prompt.py` 프롬프트에 유효 목록 주입 + `generate_actors()` / `generate_enemies()`에서 후처리 검증.

---

## 1. 캐릭터 스프라이트 (`characterName` + `characterIndex`)

`img/characters/` 디렉터리. `Actors.json[].characterName` 및 이벤트 페이지 `image.characterName`.

### 접두사 규칙

| 접두사 | 의미 | index 범위 |
|--------|------|-----------|
| 없음 | 일반 캐릭터 시트 (1파일=8캐릭터, 4열×2행) | 0~7 |
| `!` | 오브젝트형 (열기/닫기 애니메이션, 컬럼별 다른 디자인) | **0~7** |
| `$` | 빅 캐릭터 (2배 크기, 1파일=4캐릭터, 2열×2행) | **0~3** |
| `!$` | 빅 오브젝트 (게이트 등, 1파일=3디자인) | **0~2** |

### 실제 존재 파일 전체

#### 일반 캐릭터 (index 0~7)

| 파일명 | 용도 |
|--------|------|
| `Actor1` | 주인공/동료급 — 남성 스타일 |
| `Actor2` | 주인공/동료급 — 여성/다양한 스타일 |
| `Actor3` | 주인공/동료급 — 전사/판타지 스타일 |
| `People1` | 마을 주민, 상인, 일반 NPC |
| `People2` | 다양한 직업 NPC |
| `People3` | 귀족, 승려형 NPC |
| `People4` | 특수 NPC (노인, 어린이 등) |
| `Evil` | 악당, 보스, 다크 캐릭터 |
| `Monster` | 맵 위 몬스터 이벤트용 (8종 몬스터) |
| `Nature` | 자연물/정령형 |
| `Vehicle` | 탈것 (배, 비행선, 말) |
| `SF_Actor1` | SF 주인공/동료 |
| `SF_Actor2` | SF 두 번째 시리즈 |
| `SF_Actor3` | SF 세 번째 시리즈 |
| `SF_People1` | SF 배경 일반 시민 |
| `SF_People2` | SF 직업군 NPC |
| `SF_People3` | SF 특수 NPC |
| `SF_Monster` | SF 배경 몬스터 이벤트용 |
| `SF_Vehicle` | SF 탈것 |
| `Damage1` / `Damage2` / `Damage3` | 데미지 수치 (시스템용) |
| `SF_Damage1` / `SF_Damage2` | SF 데미지 수치 (시스템용) |

#### 오브젝트형 (! 접두사, index 0~7로 디자인 선택)

| 파일명 | 주요 index별 내용 |
|--------|-----------------|
| `!Chest` | 0=빨강, 1=금색, 2=초록, 3=파랑 뚜껑 보물상자, 4~7=기타 변형 |
| `!Crystal` | 0=빨강, 1=주황, 2=초록, 3=보라, 4=흰색, 5=파랑 크리스탈 |
| `!Door1` | 0=철제 대문, 1=아치형 나무문, 하단=실내문/창문/철책 |
| `!Door2` | 소형 보석/원형 아이콘 시리즈 |
| `!Flame` | 촛불, 횃불, 마법 불꽃/불기둥, 연기 이펙트 |
| `!Other1` | 돌덩이(갈색/검정/흰색/검정), 원통형 컨테이너 |
| `!Other2` | 불꽃·물·불기둥 이펙트, 황금/흰색 조각상 |
| `!Switch1` | 0~3=레버형(빨강/노랑/초록/파랑 손잡이), 4~7=버튼형 |
| `!Switch2` | 다른 스타일 스위치/버튼 |
| `!Weapon` | 무기 오브젝트 |
| `!SF_Chest` | SF 보물상자 |
| `!SF_Door1` | 상단=SF 대형 슬라이딩 도어, 하단=컬러별 패널 도어 |
| `!SF_Door2` | SF 두 번째 문 시리즈 |
| `!SF_Switch1` | SF 스위치 |

#### 빅 캐릭터 ($ 접두사, 2배 크기, index 0~3)

| 파일명 | index별 내용 |
|--------|------------|
| `$BigMonster1` | 0=뿔달린 마왕, 1=트리언트, 2=딱정벌레, 3=히드라 |
| `$BigMonster2` | index 0~3 대형 몬스터 4종 |

#### 빅 오브젝트 게이트 (!$ 접두사, index 0~2)

| 파일명 | index별 내용 |
|--------|------------|
| `!$Gate1` | 0=황금 아치문, 1=목재 성문, 2=크리스탈 포탈 |
| `!$Gate2` | 0=파란 석재문, 1=어두운 장식문, 2=갈색 목재문 |
| `!$SF_Gate1` | SF 게이트 3종 |
| `!$SF_Gate2` | SF 게이트 3종 |
| `!$SF_Gate3` | SF 게이트 3종 |

---

## 2. 얼굴 이미지 (`faceName` + `faceIndex`)

`img/faces/` 디렉터리. 1파일 = 8얼굴 (4열×2행, index 0~7).
`Actors.json[].faceName` + `faceIndex`.

### 실제 존재 파일 전체 (15개)

| 파일명 | 설명 |
|--------|------|
| `Actor1` | 젊은 주인공 스타일 |
| `Actor2` | 여성/다양한 주인공 스타일 |
| `Actor3` | 전사/기사 스타일 |
| `People1` | 마을 주민 |
| `People2` | 다양한 직업 주민 |
| `People3` | 귀족/성직자형 |
| `People4` | 특수 NPC |
| `Evil` | 악당/다크 캐릭터 |
| `Monster` | 몬스터/괴물 얼굴 |
| `Nature` | 자연물/정령형 |
| `SF_Actor1` | SF 주인공 |
| `SF_Actor2` | SF 두 번째 주인공 |
| `SF_Actor3` | SF 세 번째 주인공 |
| `SF_Monster` | SF 몬스터 얼굴 |
| `SF_People1` | SF 시민 |

> **Actor4~8은 존재하지 않는다.** 이전 문서 오류.

---

## 3. SV 전투 스프라이트 (`battlerName` — 액터용)

`img/sv_actors/` 디렉터리. `Actors.json[].battlerName`.

### 실제 존재 파일 (40개)

| 시리즈 | 존재하는 번호 |
|--------|-------------|
| `Actor1` | `Actor1_1` ~ `Actor1_8` (8개) |
| `Actor2` | `Actor2_1` ~ `Actor2_8` (8개) |
| `Actor3` | **`Actor3_5` ~ `Actor3_8` (4개만)** — 1~4 없음 |
| `SF_Actor1` | `SF_Actor1_1` ~ `SF_Actor1_8` (8개) |
| `SF_Actor2` | `SF_Actor2_1` ~ `SF_Actor2_8` (8개) |
| `SF_Actor3` | **`SF_Actor3_5` ~ `SF_Actor3_8` (4개만)** — 1~4 없음 |

> `battlerName` = `""` (빈 문자열)도 유효 — SV 전투 미사용.

---

## 4. 적 전투 이미지 (`battlerName` — 적용)

`img/enemies/` 디렉터리 (정면뷰) + `img/sv_enemies/` (사이드뷰).
`Enemies.json[].battlerName`. 총 105개 파일.

### 판타지 계열 (일부)

`Goblin`, `Dragon`, `Lich`, `Zombie`, `Witch`, `Demon`, `Harpy`, `Medusa`,
`Unicorn`, `Treant`, `Siren`, `Berserker`, `Birdman`, `Blackknight`,
`Captain`, `Crow`, `Darkelf`, `Demoncount`, `Demonpot`, `Evilbook`,
`Evilgod`, `Foxman`, `Gatekeeper`, `Gnome`, `Goddess`, `Hakutaku`,
`Highking`, `Hydra`, `Ketos`, `Kraken`, `Machinerybee`, `Matango`,
`Mechascorpion`, `Mercenary`, `Mimic`, `Petitdevil`, `Salamander`,
`Sandworm`, `Sorcerer`, `Stoneknight`, `Sylph`, `Tigerbunny`, `Undine`,
`Wolfman`, `Wraith`, `Caitsith`, `Crab`, `Demon_metamorphosis`,
`Frilledlizard`, `God_of_light`, `Goddess_of_death`, `Hi_monster`,
`Oddegg`, `Plasma`, `Sailor`

### SF 계열

`SF_Agent`, `SF_Anaconda`, `SF_Armygorilla`, `SF_Armymonkey`, `SF_Blueogre`,
`SF_Boss`, `SF_Brownbear`, `SF_Cyborg`, `SF_Demon_of_universe`, `SF_Drone`,
`SF_Enmadaio`, `SF_Evilteddybear`, `SF_Hannyamask`, `SF_Hermit`, `SF_Jiangshi`,
`SF_Kamaitachi`, `SF_Kappa`, `SF_Madclown`, `SF_Madscientist`, `SF_Mafia`,
`SF_Mechasphere`, `SF_Phoenix`, `SF_Redogre`, `SF_Securityrobot`, `SF_Shadow`,
`SF_Skullmask`, `SF_Slaughterrobot`, `SF_Specialforces`, `SF_Talkingmuppet`,
`SF_Timebomb`, `SF_Whitewolf`, `SF_Will_o_the_wisp`, `SF_Wolf`,
`SF_Workrobot`, `SF_Zombiedog`

### Actor형 인간 적

`Actor1_3` ~ `Actor1_6`, `Actor2_1` ~ `Actor2_7`, `Actor3_1` ~ `Actor3_4`

> **`Slime`은 존재하지 않는다.** 이전 문서/프롬프트 오류.
> 전체 목록: `asset_generator.py`의 `VALID_BATTLER_NAMES` frozenset 참조.

---

## 5. 전투 배경

### battleback1Name — `img/battlebacks1/` (바닥 레이어, 51개)

`Castle1`, `Castle2`, `Castle3`, `Clouds`, `Cobblestones1`~`5`,
`Colosseum`, `Crystal`, `Cyberspace`, `DecorativeTile1`, `DecorativeTile2`,
`DemonCastle1`~`3`, `DemonicWorld`, `Desert`, `Dirt`, `DirtCave`, `DirtField`,
`Fort1`, `Fort2`, `Grassland`, `GrassMaze`, `Ground1`, `Ground2`,
`IceCave`, `IceMaze`, `Lava1`, `Lava2`, `LavaCave`, `PoisonSwamp`,
`Road1`~`3`, `RockCave`, `Sand`, `Ship`, `Smoke`, `Snowfield`, `Space`,
`Stone1`~`3`, `Temple`, `Tent`, `Wasteland`, `Wood1`, `Wood2`

### battleback2Name — `img/battlebacks2/` (벽/원경 레이어, 50개)

`Brick`, `Bridge`, `Castle1`~`3`, `Cliff`, `Clouds`, `Colosseum`,
`Crystal`, `Cyberspace`, `DarkSpace`, `DemonCastle1`~`3`, `DemonicWorld`,
`Desert`, `DirtCave`, `Forest`, `Fort1`, `Fort2`, `Grassland`, `GrassMaze`,
`IceCave`, `IceMaze`, `Lava`, `LavaCave`, `PoisonSwamp`, `Port`,
`RockCave`, `Room1`~`3`, `Ruins1`~`3`, `Ship`, `Smoke`, `Snowfield`,
`Stone1`~`3`, `Temple`, `Tent`, `Tower`, `Town1`~`5`, `Wasteland`

### 맵 타입별 권장 조합 (실제 존재하는 파일명 기준)

| 맵 타입 | battleback1Name | battleback2Name |
|---------|----------------|----------------|
| `town` | `Cobblestones1` | `Town1` |
| `dungeon` | `DirtCave` | `RockCave` |
| `boss` | `Stone1` | `DemonCastle1` |
| SF 던전 | `Cyberspace` | `DarkSpace` |
| 설원 | `Snowfield` | `IceCave` |
| 용암 | `Lava1` | `LavaCave` |

> **`Village`, `DungeonA4`, `DungeonB` 등은 존재하지 않는다.** 이전 문서 오류.

---

## 6. 코드 상수 (asset_generator.py 기준)

### 액터 이미지 검증 상수

```python
# img/characters/ 실제 파일 기준
VALID_CHARACTER_NAMES: frozenset[str] = frozenset([
    "Actor1", "Actor2", "Actor3",
    "People1", "People2", "People3", "People4",
    "Evil", "Monster", "Nature", "Vehicle",
    "SF_Actor1", "SF_Actor2", "SF_Actor3",
    "SF_People1", "SF_People2", "SF_People3",
    "SF_Monster", "SF_Vehicle",
])

# img/faces/ 실제 파일 기준
VALID_FACE_NAMES: frozenset[str] = frozenset([
    "Actor1", "Actor2", "Actor3",
    "People1", "People2", "People3", "People4",
    "Evil", "Monster", "Nature",
    "SF_Actor1", "SF_Actor2", "SF_Actor3",
    "SF_Monster", "SF_People1",
])

# img/sv_actors/ 실제 파일 기준 (Actor3·SF_Actor3는 5~8만 존재)
VALID_ACTOR_BATTLER_NAMES: frozenset[str] = frozenset([
    *(f"Actor1_{i}" for i in range(1, 9)),
    *(f"Actor2_{i}" for i in range(1, 9)),
    *(f"Actor3_{i}" for i in range(5, 9)),
    *(f"SF_Actor1_{i}" for i in range(1, 9)),
    *(f"SF_Actor2_{i}" for i in range(1, 9)),
    *(f"SF_Actor3_{i}" for i in range(5, 9)),
    "",  # SV 전투 미사용
])
```

### 이벤트 캐릭터 검증 상수

```python
# generation_validator.py의 _VALID_CHARACTER_NAMES (이벤트용)
# characters/ 폴더의 모든 오브젝트·캐릭터 파일 포함
_VALID_CHARACTER_NAMES: frozenset[str] = frozenset({
    # 일반 캐릭터
    "Actor1", "Actor2", "Actor3",
    "People1", "People2", "People3", "People4",
    "Evil", "Monster", "Nature", "Vehicle",
    "Damage1", "Damage2", "Damage3",
    # SF 캐릭터
    "SF_Actor1", "SF_Actor2", "SF_Actor3",
    "SF_People1", "SF_People2", "SF_People3",
    "SF_Monster", "SF_Vehicle", "SF_Damage1", "SF_Damage2",
    # 오브젝트 (! 접두사)
    "!Chest", "!Crystal", "!Door1", "!Door2",
    "!Flame", "!Other1", "!Other2",
    "!Switch1", "!Switch2", "!Weapon",
    "!SF_Chest", "!SF_Door1", "!SF_Door2", "!SF_Switch1",
    # 빅 캐릭터 ($ 접두사)
    "$BigMonster1", "$BigMonster2",
    # 빅 오브젝트 (!$ 접두사)
    "!$Gate1", "!$Gate2",
    "!$SF_Gate1", "!$SF_Gate2", "!$SF_Gate3",
})
```

---

## 7. 이벤트 타입별 권장 character_name

| 이벤트 타입 | 권장 character_name | index |
|------------|---------------------|-------|
| NPC (마을 주민) | `People1` ~ `People4` | 0~7 |
| NPC (주인공급) | `Actor1` ~ `Actor3` | 0~7 |
| NPC (악당) | `Evil` | 0~7 |
| NPC (몬스터형) | `Monster` | 0~7 |
| BattleEvent (일반) | `Monster` | 0~7 |
| BattleEvent (대형 보스) | `$BigMonster1` | 0~3 |
| ChestEvent | `!Chest` | 0=빨강, 1=금색, 2=초록, 3=파랑 |
| TransferEvent (기본) | `!Crystal` | 0~5=색상별 |
| TransferEvent (건물/던전 입구) | `!Door1` | 0=철제문, 1=아치형 |
| TransferEvent (보스 방) | `!$Gate1` | 0=황금문, 2=포탈 |
| TransferEvent (SF) | `!SF_Door1` | 0=슬라이딩 |
| TransferEvent (투명 자동) | `""` | — |
| ShopEvent | `People1` ~ `People4` | 0~7 |

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|---------|
| 2026-04-07 | 실제 이미지 전수 확인 후 전면 재작성. Actor4~8, Slime, Village 등 존재하지 않는 파일명 전부 제거. 오브젝트 index 규칙 수정 (항상 0 → 0~7). |
| 2026-04-06 | 최초 작성 (부정확한 내용 포함) |
