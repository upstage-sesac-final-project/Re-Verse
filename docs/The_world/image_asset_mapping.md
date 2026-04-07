# RPG Maker MZ 이미지 에셋 매핑 레퍼런스

> 기준: `storage/games/base_game/img/` 실제 파일 목록 전수 분석
> 작성일: 2026-04-07

---

## 개요 — 폴더별 역할 및 JSON 필드 대응

| 폴더 | 역할 | JSON 필드 |
|------|------|-----------|
| `characters/` | 맵 위 이벤트/NPC 보행 스프라이트 | `Actors.json[].characterName` + `characterIndex` <br> 이벤트 페이지 `image.characterName` + `image.characterIndex` |
| `faces/` | 대화창 얼굴 이미지 (8개 묶음 시트) | `Actors.json[].faceName` + `faceIndex` <br> 이벤트 커맨드 101 파라미터[0] |
| `pictures/` | 얼굴 시트를 1개씩 분리한 전신/반신 이미지 | `ShowPicture` 커맨드 (code 231), UI 연출용 |
| `sv_actors/` | 사이드뷰 전투 액터 모션 스프라이트 | `Actors.json[].battlerName` |
| `enemies/` | 전투 화면 적 이미지 (정면뷰, 1개씩) | `Enemies.json[].battlerName` |
| `sv_enemies/` | 사이드뷰 전투 적 스프라이트 (sv_battle 플러그인용) | `Enemies.json[].battlerName` (sv 배틀 시 동일 파일명) |
| `battlebacks1/` | 전투 배경 — 바닥 레이어 | `Tilesets.json[].battlebacks1Name` / 맵 설정 |
| `battlebacks2/` | 전투 배경 — 벽/원경 레이어 | `Tilesets.json[].battlebacks2Name` |
| `tilesets/` | 맵 타일셋 PNG | `Tilesets.json[].tilesetNames[]` |
| `titles1/` | 타이틀 화면 배경 | `System.json` title1Name |
| `titles2/` | 타이틀 화면 로고/장식 | `System.json` title2Name |
| `parallaxes/` | 원경 스크롤 배경 | 맵 `Map*.json` parallaxName |

---

## 1. characters/ — 맵 이벤트 스프라이트

### 파일 명명 규칙

| 접두사 | 의미 | characterIndex |
|--------|------|----------------|
| 없음 | 일반 캐릭터 시트 — 1개 파일에 8캐릭터 (4열×2행) | 0~7 |
| `!` | 오브젝트형 — 열기/닫기 애니메이션, 컬럼별로 다른 디자인 | **0~7** (디자인 선택) |
| `$` | 빅 스프라이트 — 2배 크기 캐릭터, 1파일에 4캐릭터 (2열×2행) | **0~3** |
| `!$` | 빅 오브젝트 — 게이트/문 등 대형 오브젝트, 1파일에 3디자인 | **0~2** |

> **주의**: `!` 접두사 스프라이트는 "index 항상 0"이 아님. 각 컬럼이 다른 디자인(색상/스타일)이며
> characterIndex로 선택함. 예: `!Chest` index 0=빨강, 1=금색, 2=초록, 3=파랑, 4~7=기타 변형.

### 실제 존재하는 파일 전체 목록

#### 일반 캐릭터 (index 0~7)

| 파일명 (확장자 제외) | 용도 | 권장 index |
|---------------------|------|-----------|
| `Actor1` | 주인공/동료급 — 남성 스타일 | 0~7 자유 |
| `Actor2` | 주인공/동료급 — 여성/다양한 스타일 | 0~7 자유 |
| `Actor3` | 주인공/동료급 — 전사/판타지 스타일 | 0~7 자유 |
| `People1` | 마을 주민, 상인, 일반 NPC | 0~7 자유 |
| `People2` | 다양한 직업 NPC (기사, 농부 등) | 0~7 자유 |
| `People3` | 귀족, 승려, 마법사형 NPC | 0~7 자유 |
| `People4` | 특수 NPC (노인, 어린이 등) | 0~7 자유 |
| `Evil` | 악당, 보스, 다크 캐릭터 | 0~7 자유 |
| `Monster` | 맵 위 일반 몬스터 이벤트용 | 0~7 자유 |
| `Nature` | 자연물 (나무, 버섯형 등) | 0~7 자유 |
| `Vehicle` | 탈것 (배, 비행선, 말) | 0~7 자유 |
| `Damage1` | 데미지 수치 스프라이트 | 시스템용 |
| `Damage2` | 데미지 수치 스프라이트 | 시스템용 |
| `Damage3` | 데미지 수치 스프라이트 | 시스템용 |

#### SF 계열 일반 캐릭터 (index 0~7)

| 파일명 | 용도 |
|--------|------|
| `SF_Actor1` | SF 주인공/동료 — 캐주얼 SF |
| `SF_Actor2` | SF 주인공/동료 — 다양한 스타일 |
| `SF_Actor3` | SF 주인공/동료 — 특수 스타일 |
| `SF_People1` | SF 배경 일반 시민 |
| `SF_People2` | SF 직업군 (군인, 기술자 등) |
| `SF_People3` | SF 특수 NPC |
| `SF_Monster` | SF 배경 몬스터 이벤트용 |
| `SF_Vehicle` | SF 탈것 (로봇, 드론형) |
| `SF_Damage1` | SF 데미지 수치 |
| `SF_Damage2` | SF 데미지 수치 |

#### 오브젝트형 (! 접두사, index 0~7로 디자인 선택)

| 파일명 | index별 내용 (직접 확인) |
|--------|------------------------|
| `!Chest` | 0=빨강뚜껑, 1=금색뚜껑, 2=초록뚜껑, 3=파랑뚜껑, 4~7=기타 변형(철제 등) |
| `!Crystal` | index별 크리스탈 색상/형태 |
| `!Door1` | 0=철제 대문, 1=아치형 나무문, 2~=기타 문 스타일 / 하단 행은 실내문·창문·철책 |
| `!Door2` | 두 번째 문 시리즈 |
| `!Flame` | 불꽃 이펙트 변형 |
| `!Other1` | 기타 오브젝트 1 |
| `!Other2` | 기타 오브젝트 2 |
| `!Switch1` | 0~3=레버형(빨강/노랑/초록/파랑 손잡이), 4~7=버튼형(빨강/노랑/초록/파랑) |
| `!Switch2` | 다른 스타일 스위치/버튼 |
| `!Weapon` | 무기 오브젝트 |
| `!SF_Chest` | SF 보물상자 |
| `!SF_Door1` | SF 문 |
| `!SF_Door2` | SF 두 번째 문 |
| `!SF_Switch1` | SF 스위치 |

#### 빅 몬스터 ($ 접두사, 2배 크기, index 0~3)

| 파일명 | index별 내용 (직접 확인) |
|--------|------------------------|
| `$BigMonster1` | 0=뿔달린 마왕(자주색), 1=트리언트(초록), 2=딱정벌레형, 3=히드라(다두룡) |
| `$BigMonster2` | index 0~3 각기 다른 대형 몬스터 |

#### 빅 오브젝트 게이트 (!$ 접두사, index 0~2)

| 파일명 | index별 내용 (직접 확인) |
|--------|------------------------|
| `!$Gate1` | 0=금장식 아치문, 1=목재 대문, 2=빨강/크리스탈 포탈 |
| `!$Gate2` | 0=파란 석재문, 1=어두운 장식문, 2=갈색 목재문 |
| `!$SF_Gate1` | SF 게이트 3종 |
| `!$SF_Gate2` | SF 게이트 3종 |
| `!$SF_Gate3` | SF 게이트 3종 |

### 이벤트 타입별 권장 character_name

| 이벤트 타입 | 권장 character_name | 비고 |
|------------|---------------------|------|
| NPC (마을 주민) | `People1` ~ `People4` | index 0~7로 다양화 |
| NPC (주인공급) | `Actor1` ~ `Actor3` | |
| NPC (악당) | `Evil` | |
| NPC (몬스터형) | `Monster` 또는 `SF_Monster` | |
| BattleEvent (일반 몬스터) | `Monster` | index 0~7로 종류 구분 |
| BattleEvent (대형 보스) | `$BigMonster1` 또는 `$BigMonster2` | index **0~3** 선택 |
| ChestEvent | `!Chest` | index **0~3** = 색상 선택 (0=빨강, 1=금색, 2=초록, 3=파랑) |
| TransferEvent (투명 워프) | `""` (빈 문자열) | 플레이어에게 안 보임 |
| TransferEvent (문 워프) | `!Door1` 또는 `!Door2` | index 0 고정 |
| ShopEvent | `People1` ~ `People4` | 상점 NPC 외형 |
| EndingEvent | `""` 또는 `Actor1` | auto_run이므로 보통 투명 |

---

## 2. faces/ — 대화창 얼굴 이미지 (faceName + faceIndex)

**규칙**: 1개 파일 = 8개 얼굴, 좌→우 4개, 위→아래 2행 (index 0~7)

### 실제 존재하는 파일

| 파일명 | 얼굴 스타일 | 권장 사용 | index 범위 |
|--------|-----------|---------|-----------|
| `Actor1` | 젊은 남성 주인공 스타일 | 플레이어 액터 | 0~7 |
| `Actor2` | 여성/다양한 주인공 스타일 | 플레이어 액터 | 0~7 |
| `Actor3` | 전사/기사 스타일 | 플레이어 액터, 기사 NPC | 0~7 |
| `People1` | 마을 주민 | 일반 NPC | 0~7 |
| `People2` | 다양한 직업 주민 | NPC | 0~7 |
| `People3` | 귀족/성직자형 | NPC | 0~7 |
| `People4` | 특수 NPC | NPC | 0~7 |
| `Evil` | 악당/다크 캐릭터 | 보스, 적 NPC | 0~7 |
| `Monster` | 몬스터/괴물 얼굴 | 몬스터 NPC | 0~7 |
| `Nature` | 자연물/정령형 | 정령 NPC | 0~7 |
| `SF_Actor1` | SF 주인공 남성 | SF 배경 액터 | 0~7 |
| `SF_Actor2` | SF 주인공 여성/다양 | SF 배경 액터 | 0~7 |
| `SF_Actor3` | SF 주인공 특수 | SF 배경 액터 | 0~7 |
| `SF_Monster` | SF 몬스터 얼굴 | SF 배경 몬스터 NPC | 0~7 |
| `SF_People1` | SF 시민 | SF 배경 NPC | 0~7 |

> **주의**: faces 파일과 characters 파일은 이름이 같아도 별개. faceName과 characterName에 같은 값(`"Actor1"` 등)을 써도 참조 폴더가 다름.

---

## 3. pictures/ — 1인 얼굴/전신 이미지 (개별 PNG)

`faces/` 시트를 1개씩 분리한 개별 이미지. `ShowPicture` 이벤트 커맨드(code 231)로 화면에 표시.

**파일명 규칙**: `{시트명}_{1~8}.png` — faces의 faceIndex+1에 대응

| 시트명 | 분리 파일 | 총 개수 |
|--------|----------|--------|
| `Actor1` | `Actor1_1.png` ~ `Actor1_8.png` | 8 |
| `Actor2` | `Actor2_1.png` ~ `Actor2_8.png` | 8 |
| `Actor3` | `Actor3_1.png` ~ `Actor3_8.png` | 8 |
| `People1` | `People1_1.png` ~ `People1_8.png` | 8 |
| `People2` | `People2_1.png` ~ `People2_8.png` | 8 |
| `People3` | `People3_1.png` ~ `People3_8.png` | 8 |
| `People4` | `People4_1.png` ~ `People4_8.png` | 8 |
| `Evil` | `Evil_1.png` ~ `Evil_8.png` | 8 |
| `Monster` | `Monster_1.png` ~ `Monster_8.png` | 8 |
| `Nature` | `Nature_1.png` ~ `Nature_8.png` | 8 |
| `SF_Actor1` | `SF_Actor1_1.png` ~ `SF_Actor1_8.png` | 8 |
| `SF_Actor2` | `SF_Actor2_1.png` ~ `SF_Actor2_8.png` | 8 |
| `SF_Actor3` | `SF_Actor3_1.png` ~ `SF_Actor3_8.png` | 8 |
| `SF_Monster` | `SF_Monster_1.png` ~ `SF_Monster_8.png` | 8 |
| `SF_People1` | `SF_People1_1.png` ~ `SF_People1_8.png` | 8 |

---

## 4. sv_actors/ — 사이드뷰 전투 액터 스프라이트 (battlerName)

사이드뷰 배틀 시스템에서 액터 전투 모션을 표시. `Actors.json[].battlerName` 필드에 파일명(확장자 제외) 기입.

**파일명 규칙**: `{시트명}_{번호}.png` 형식 (번호는 1~8)

### 실제 존재하는 파일

| 시리즈 | 존재하는 번호 | 비고 |
|--------|------------|------|
| `Actor1` | 1~8 (`Actor1_1` ~ `Actor1_8`) | 완전한 시리즈 |
| `Actor2` | 1~8 (`Actor2_1` ~ `Actor2_8`) | 완전한 시리즈 |
| `Actor3` | 5~8만 (`Actor3_5` ~ `Actor3_8`) | 1~4 없음 주의 |
| `SF_Actor1` | 1~8 | SF 주인공 완전 시리즈 |
| `SF_Actor2` | 1~8 | SF 두 번째 시리즈 |
| `SF_Actor3` | 5~8만 | SF Actor3도 5~8만 존재 |

> `Actors.json[].battlerName` 사용 가능 값:
> `Actor1_1`~`Actor1_8`, `Actor2_1`~`Actor2_8`, `Actor3_5`~`Actor3_8`,
> `SF_Actor1_1`~`SF_Actor1_8`, `SF_Actor2_1`~`SF_Actor2_8`, `SF_Actor3_5`~`SF_Actor3_8`

---

## 5. enemies/ — 전투 화면 적 이미지 (battlerName)

1개 파일 = 1마리 적. `Enemies.json[].battlerName` 필드에 파일명(확장자 제외) 기입.

### 판타지 계열

| 파일명 | 이미지 |
|--------|--------|
| `Actor1_3` ~ `Actor1_6` | 인간형 적 (Actor1 시트 기반) |
| `Actor2_1` ~ `Actor2_7` | 인간형 적 (Actor2 시트 기반) |
| `Actor3_1` ~ `Actor3_4` | 인간형 적 (Actor3 시트 기반) |
| `Berserker` | 광전사 |
| `Birdman` | 조인 |
| `Blackknight` | 흑기사 |
| `Caitsith` | 요정 고양이 |
| `Captain` | 캡틴/선장 |
| `Crab` | 게 |
| `Crow` | 까마귀 |
| `Darkelf` | 다크 엘프 |
| `Demon` | 악마 |
| `Demon_metamorphosis` | 변신 악마 |
| `Demoncount` | 마왕 |
| `Demonpot` | 항아리 악마 |
| `Dragon` | 드래곤 |
| `Evilbook` | 마도서 |
| `Evilgod` | 사신 |
| `Foxman` | 여우인간 |
| `Frilledlizard` | 도마뱀 |
| `Gatekeeper` | 문지기 |
| `Gnome` | 노움 |
| `Goblin` | 고블린 |
| `God_of_light` | 광신 |
| `Goddess` | 여신 |
| `Goddess_of_death` | 죽음의 여신 |
| `Hakutaku` | 해마 |
| `Harpy` | 하피 |
| `Hi_monster` | 상위 몬스터 |
| `Highking` | 대왕 |
| `Hydra` | 히드라 |
| `Ketos` | 케토스 |
| `Kraken` | 크라켄 |
| `Lich` | 리치 |
| `Machinerybee` | 기계 벌 |
| `Matango` | 마탕고 (버섯몬스터) |
| `Mechascorpion` | 기계 전갈 |
| `Medusa` | 메두사 |
| `Mercenary` | 용병 |
| `Mimic` | 미믹 |
| `Oddegg` | 이상한 알 |
| `Petitdevil` | 소악마 |
| `Plasma` | 플라즈마 |
| `Sailor` | 선원 |
| `Salamander` | 살라만더 |
| `Sandworm` | 모래벌레 |
| `Siren` | 사이렌 |
| `Sorcerer` | 마법사 |
| `Stoneknight` | 석상 기사 |
| `Sylph` | 실프 |
| `Tigerbunny` | 호랑이 토끼 |
| `Treant` | 트리언트 |
| `Undine` | 운디네 |
| `Unicorn` | 유니콘 |
| `Witch` | 마녀 |
| `Wolfman` | 늑대인간 |
| `Wraith` | 망령 |
| `Zombie` | 좀비 |

### SF 계열

| 파일명 | 이미지 |
|--------|--------|
| `SF_Agent` | SF 요원 |
| `SF_Anaconda` | 아나콘다 |
| `SF_Armygorilla` | 군사 고릴라 |
| `SF_Armymonkey` | 군사 원숭이 |
| `SF_Blueogre` | 파란 오거 |
| `SF_Boss` | SF 보스 |
| `SF_Brownbear` | 갈색 곰 |
| `SF_Cyborg` | 사이보그 |
| `SF_Demon_of_universe` | 우주 악마 |
| `SF_Drone` | 드론 |
| `SF_Enmadaio` | 염마대왕 |
| `SF_Evilteddybear` | 악의 테디베어 |
| `SF_Hannyamask` | 하냐 마스크 |
| `SF_Hermit` | 은둔자 |
| `SF_Jiangshi` | 강시 |
| `SF_Kamaitachi` | 카마이타치 |
| `SF_Kappa` | 갓파 |
| `SF_Madclown` | 광대 |
| `SF_Madscientist` | 광과학자 |
| `SF_Mafia` | 마피아 |
| `SF_Mechasphere` | 기계 구체 |
| `SF_Phoenix` | 불사조 |
| `SF_Redogre` | 빨간 오거 |
| `SF_Securityrobot` | 경비 로봇 |
| `SF_Shadow` | 그림자 |
| `SF_Skullmask` | 해골 마스크 |
| `SF_Slaughterrobot` | 학살 로봇 |
| `SF_Specialforces` | 특수부대 |
| `SF_Talkingmuppet` | 말하는 인형 |
| `SF_Timebomb` | 시한폭탄 |
| `SF_Whitewolf` | 흰 늑대 |
| `SF_Will_o_the_wisp` | 도깨비불 |
| `SF_Wolf` | 늑대 |
| `SF_Workrobot` | 작업 로봇 |
| `SF_Zombiedog` | 좀비 개 |

---

## 6. sv_enemies/ — 사이드뷰 전투 적 스프라이트

`enemies/`와 **거의 동일한 파일 목록** (이미지만 사이드뷰용으로 다름).
`sv_enemies/SF_ArmyGorilla.png` (대문자 G)처럼 대소문자가 미묘하게 다를 수 있으므로 실제 파일명 기준 사용.

사이드뷰 배틀 플러그인 사용 시 `Enemies.json[].battlerName`이 `sv_enemies/` 파일도 동일 이름으로 참조함.

---

## 7. battlebacks1/ & battlebacks2/ — 전투 배경

### battlebacks1 (바닥 레이어) — 실제 파일 목록

`Castle1`, `Castle2`, `Castle3`, `Clouds`, `Cobblestones1`~`5`, `Colosseum`,
`Crystal`, `Cyberspace`, `DecorativeTile1`, `DecorativeTile2`,
`DemonCastle1`~`3`, `DemonicWorld`, `Desert`, `Dirt`, `DirtCave`, `DirtField`,
`Fort1`, `Fort2`, `Grassland`, `GrassMaze`, `Ground1`, `Ground2`,
`IceCave`, `IceMaze`, `Lava1`, `Lava2`, `LavaCave`, `PoisonSwamp`,
`Road1`~`3`, `RockCave`, `Sand`, `Ship`, `Smoke`, `Snowfield`, `Space`,
`Stone1`~`3`, `Temple`, `Tent`, `Wasteland`, `Wood1`, `Wood2`

### battlebacks2 (벽/원경 레이어) — 실제 파일 목록

`Brick`, `Bridge`, `Castle1`~`3`, `Cliff`, `Clouds`, `Colosseum`,
`Crystal`, `Cyberspace`, `DarkSpace`, `DemonCastle1`~`3`, `DemonicWorld`,
`Desert`, `DirtCave`, `Forest`, `Fort1`, `Fort2`, `Grassland`, `GrassMaze`,
`IceCave`, `IceMaze`, `Lava`, `LavaCave`, `PoisonSwamp`, `Port`,
`RockCave`, `Room1`~`3`, `Ruins1`~`3`, `Ship`, `Smoke`, `Snowfield`,
`Stone1`~`3`, `Temple`, `Tent`, `Tower`, `Town1`~`5`, `Wasteland`

### 맵 타입별 권장 조합

| 맵 타입 | battlebacks1 | battlebacks2 |
|---------|-------------|-------------|
| `town` | `Cobblestones1` | `Town1` |
| `dungeon` | `DirtCave` | `RockCave` |
| `boss` | `Stone1` | `DemonCastle1` |
| SF 던전 | `Cyberspace` | `DarkSpace` |

---

## 8. tilesets/ — 맵 타일셋

### Outside (야외) 계열

| 파일명 | 내용 |
|--------|------|
| `Outside_A1` | 야외 자동타일 (물/애니) |
| `Outside_A2` | 야외 지형 자동타일 |
| `Outside_A3` | 야외 건물 자동타일 |
| `Outside_A4` | 야외 벽 자동타일 |
| `Outside_A5` | 야외 소품 |
| `Outside_B` | 야외 B 타일 |
| `Outside_C` | 야외 C 타일 |

### Inside (실내) 계열

| 파일명 | 내용 |
|--------|------|
| `Inside_A1` | 실내 바닥 자동타일 |
| `Inside_A2` | 실내 지형 자동타일 |
| `Inside_A4` | 실내 벽 자동타일 |
| `Inside_A5` | 실내 소품 |
| `Inside_B` | 실내 B 타일 |
| `Inside_C` | 실내 C 타일 |

### Dungeon (던전) 계열

| 파일명 | 내용 |
|--------|------|
| `Dungeon_A1` | 던전 바닥 자동타일 |
| `Dungeon_A2` | 던전 지형 |
| `Dungeon_A4` | 던전 벽 |
| `Dungeon_A5` | 던전 소품 |
| `Dungeon_B` | 던전 B 타일 |
| `Dungeon_C` | 던전 C 타일 |

### World (월드맵) 계열

| 파일명 | 내용 |
|--------|------|
| `World_A1` | 월드맵 바다/강 |
| `World_A2` | 월드맵 지형 |
| `World_B` | 월드맵 B |
| `World_C` | 월드맵 C |

### SF 계열

`SF_Inside_A4`, `SF_Inside_B`, `SF_Inside_C`,
`SF_Outside_A3`, `SF_Outside_A4`, `SF_Outside_A5`, `SF_Outside_B`, `SF_Outside_C`

---

## 9. titles1/ & titles2/ — 타이틀 화면

### titles1 (배경 이미지)

`Beach`, `Bigtree`, `Canyon`, `FlyingIsland`, `Gate`, `Gold`, `Jungle`,
`Mansion`, `Monument`, `Mountain`, `Night`, `Oasis`, `Ruins`, `Sky`,
`Snow`, `Sword`, `Town1`, `Town2`, `Universe`, `Wasteland`

### titles2 (로고/장식)

`Floral`, `Medieval`

---

## 10. parallaxes/ — 원경 배경

`BlueSky`, `Clouds`, `DarkClouds`, `DarkSpace`, `Desert`, `DesertNight`,
`Forest`, `IslandofSky1`, `IslandofSky2`, `Lava`, `Mountains1`~`3`,
`Ocean`, `RedSky`, `River`, `SnowForest`, `Space`, `StarlitSky`,
`Twilight`, `Universe`

---

## 코드 적용 가이드

### asset_generator — Actors.json 생성 시 허용값

```python
# characterName 허용값 (characters/ 파일명, 확장자 제외)
VALID_CHARACTER_NAMES = {
    # 일반 캐릭터
    "Actor1", "Actor2", "Actor3",
    "People1", "People2", "People3", "People4",
    "Evil", "Monster", "Nature", "Vehicle",
    # SF
    "SF_Actor1", "SF_Actor2", "SF_Actor3",
    "SF_People1", "SF_People2", "SF_People3",
    "SF_Monster", "SF_Vehicle",
    # 오브젝트
    "!Chest", "!Crystal", "!Door1", "!Door2", "!Flame",
    "!Other1", "!Other2", "!Switch1", "!Switch2", "!Weapon",
    "!SF_Chest", "!SF_Door1", "!SF_Door2", "!SF_Switch1",
    # 빅
    "$BigMonster1", "$BigMonster2",
    "!$Gate1", "!$Gate2", "!$SF_Gate1", "!$SF_Gate2", "!$SF_Gate3",
}

# faceName 허용값 (faces/ 파일명)
VALID_FACE_NAMES = {
    "Actor1", "Actor2", "Actor3",
    "People1", "People2", "People3", "People4",
    "Evil", "Monster", "Nature",
    "SF_Actor1", "SF_Actor2", "SF_Actor3",
    "SF_Monster", "SF_People1",
}

# battlerName 허용값 (sv_actors/ 파일명)
VALID_BATTLER_NAMES = {
    f"Actor1_{i}" for i in range(1, 9)
} | {
    f"Actor2_{i}" for i in range(1, 9)
} | {
    f"Actor3_{i}" for i in range(5, 9)
} | {
    f"SF_Actor1_{i}" for i in range(1, 9)
} | {
    f"SF_Actor2_{i}" for i in range(1, 9)
} | {
    f"SF_Actor3_{i}" for i in range(5, 9)
}
```

### asset_generator — Enemies.json 생성 시 허용값

```python
# enemies/ 파일명 (battlerName)
VALID_ENEMY_BATTLER_NAMES = {
    # 판타지 인간형
    "Actor1_3", "Actor1_4", "Actor1_5", "Actor1_6",
    "Actor2_1", "Actor2_2", "Actor2_3", "Actor2_4", "Actor2_5", "Actor2_6", "Actor2_7",
    "Actor3_1", "Actor3_2", "Actor3_3", "Actor3_4",
    # 판타지 몬스터
    "Berserker", "Birdman", "Blackknight", "Caitsith", "Captain", "Crab",
    "Crow", "Darkelf", "Demon", "Demon_metamorphosis", "Demoncount", "Demonpot",
    "Dragon", "Evilbook", "Evilgod", "Foxman", "Frilledlizard", "Gatekeeper",
    "Gnome", "Goblin", "God_of_light", "Goddess", "Goddess_of_death", "Hakutaku",
    "Harpy", "Hi_monster", "Highking", "Hydra", "Ketos", "Kraken", "Lich",
    "Machinerybee", "Matango", "Mechascorpion", "Medusa", "Mercenary", "Mimic",
    "Oddegg", "Petitdevil", "Plasma", "Sailor", "Salamander", "Sandworm",
    "Siren", "Sorcerer", "Stoneknight", "Sylph", "Tigerbunny", "Treant",
    "Undine", "Unicorn", "Witch", "Wolfman", "Wraith", "Zombie",
    # SF 몬스터
    "SF_Agent", "SF_Anaconda", "SF_Armygorilla", "SF_Armymonkey", "SF_Blueogre",
    "SF_Boss", "SF_Brownbear", "SF_Cyborg", "SF_Demon_of_universe", "SF_Drone",
    "SF_Enmadaio", "SF_Evilteddybear", "SF_Hannyamask", "SF_Hermit", "SF_Jiangshi",
    "SF_Kamaitachi", "SF_Kappa", "SF_Madclown", "SF_Madscientist", "SF_Mafia",
    "SF_Mechasphere", "SF_Phoenix", "SF_Redogre", "SF_Securityrobot", "SF_Shadow",
    "SF_Skullmask", "SF_Slaughterrobot", "SF_Specialforces", "SF_Talkingmuppet",
    "SF_Timebomb", "SF_Whitewolf", "SF_Will_o_the_wisp", "SF_Wolf",
    "SF_Workrobot", "SF_Zombiedog",
}
```

### 이벤트 character_name 허용값 (generation_validator R24 검증 기준)

현재 `generation_validator.py`의 `_VALID_CHARACTER_NAMES` frozenset이 이 문서 기준 값을 사용함.
추가/변경 시 해당 frozenset도 동시 업데이트 필요.

---

## 기존 문서 오류 수정 사항

> `docs/The_world/rpgmaker_default_assets.md`는 실제와 다른 내용 포함 — 이 문서로 대체

| 항목 | 기존 문서 (오류) | 실제 (이미지 직접 확인) |
|------|----------------|------|
| characters 파일 | Actor4~8 존재한다고 기술 | 존재하지 않음, Actor1~3만 있음 |
| faces 파일 | Actor4~8 존재한다고 기술 | 존재하지 않음, Actor1~3만 있음 |
| objects 파일명 | `!Door`, `!Barrel` | `!Door1`, `!Door2`가 정확한 파일명 (Barrel 없음) |
| sv_actors | Actor3_1~8 모두 존재 | Actor3_5~8만 존재 (1~4 없음) |
| `!` 접두사 index | "index 항상 0" | **0~7 모두 유효** — 컬럼별로 다른 디자인/색상 선택 |
| `$BigMonster` index | "index 0" | **0~3** — 2×2 그리드에 4종 몬스터 |
| `!$Gate` index | "index 0" | **0~2** — 3열에 3종 게이트 디자인 |
