# RPG Maker MZ 데이터 스키마 레퍼런스

> game_data/game_001/data/ 내 JSON 파일별 전체 필드 정의.
> 실제 게임 데이터에서 추출한 구조 기준.
> 모든 필드명은 **camelCase**입니다 (snake_case 아님).

---

## 목차

1. [Actors.json](#actorsjson)
2. [Classes.json](#classesjson)
3. [Enemies.json](#enemiesjson)
4. [Items.json](#itemsjson)
5. [Weapons.json](#weaponsjson)
6. [Armors.json](#armorsjson)
7. [Skills.json](#skillsjson)
8. [States.json](#statesjson)
9. [Troops.json](#troopsjson)
10. [CommonEvents.json](#commoneventsjson)
11. [Tilesets.json](#tilesetsjson)
12. [Animations.json](#animationsjson)
13. [MapInfos.json](#mapinfosjson)
14. [System.json](#systemjson)
15. [MapXXX.json](#mapxxxjson)
16. [공통 서브구조](#공통-서브구조)

---

## 파일 공통 규칙

- 배열 기반 파일(Actors, Items 등): `[null, {id:1, ...}, {id:2, ...}, ...]`
  - 인덱스 0은 항상 `null`
  - 각 요소의 `id`는 배열 인덱스와 동일(초기 설정에서는!)
- 딕셔너리 기반 파일: System.json, MapXXX.json

---

## Actors.json

파티에 합류할 수 있는 플레이어 캐릭터 정의. NPC가 아님!

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| battlerName | string | [SV] 전투 스프라이트 파일명. 패턴: `Actor{숫자}_{숫자}` | `"Actor1_1"` |
| characterIndex | int | characterName 시트 내 인덱스 (0~7). characterName의 숫자보다 1 작아야 함 | `0` |
| characterName | string | 맵 보행 캐릭터 파일명. 패턴: `Actor{숫자}` | `"Actor1"` |
| classId | int | 직업 ID (Classes.json 참조, 최솟값 1) | `1` |
| equips | int[] | 초기 장비 ID 목록. 허용 길이는 해당 actor의 classId가 참조하는 Classes 설정을 따름 | `[1, 1, 0, 0, 0]` |
| faceIndex | int | faceName 시트 내 인덱스 (0~7). faceName의 숫자보다 1 작아야 함 | `0` |
| faceName | string | 얼굴 이미지 파일명. 패턴: `Actor{숫자}` | `"Actor1"` |
| traits | Trait[] | 특성 배열 (→ [Trait 구조](#trait)) | `[]` |
| initialLevel | int | 초기 레벨 (1~99, 0 불가) | `1` |
| maxLevel | int | 최대 레벨 (1~99) | `99` |
| name | string | 캐릭터 이름 | `"리드"` |
| nickname | string | 별명/칭호 | `"용사"` |
| note | string | 메모 (플러그인 태그 등) | `""` |
| profile | string | 프로필 설명 텍스트 | `"용감한 청년"` |

id는 사실 가리키는 게 없고
**목록의 순서(인덱스)**가 중요함(주인공-메인 캐릭터 결정은 맨 위에 올라온 놈이 하게 됨)

---

## Classes.json

직업(클래스) 정의. Actor의 classId로 참조됨.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| expParams | int[4] (길이 고정) | 경험치 곡선 파라미터 4개 [기본값, 추가값, 증가율A, 증가율B] | `[30, 20, 20, 40]` |
| traits | Trait[] | 직업 특성 | (배열) |
| learnings | Learning[] | 스킬 습득 목록 | `[{level:1, skillId:1, note:""}]` |
| name | string | 직업명 | `"검사"` |
| note | string | 메모 | `""` |
| params | int[8][] (바깥 배열 길이 8 고정, 안쪽 길이는 레벨 수에 따라 다름) | 레벨별 능력치 성장 곡선. 8개 능력치 x 레벨 수 | (2차원 배열) |

마찬가지로 id는 의미가 없음... 순서가 중요해ㅠㅠ


### Learning 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| level | int | 습득 레벨 (1~99) |
| note | string | 메모 |
| skillId | int | 스킬 ID (Skills.json 참조, 최솟값 1) |

---

## Skills.json

스킬/마법 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| animationId | int | 사용 시 애니메이션 ID (-1~120, -1=없음) | `-1` |
| damage | Damage | 데미지 설정 (→ [Damage 구조](#damage-구조)) | `{}` |
| description | string | 설명 | `""` |
| effects | Effect[] | 효과 배열 (→ [Effect 구조](#effect-구조)) | `[]` |
| hitType | int | 명중 유형: 0=확실한 타격, 1=물리적 공격, 2=마법 공격 | `1` |
| iconIndex | int | 아이콘 번호 | `76` |
| message1 | string | 사용 메시지 1 (`%1` = 캐릭터명). 예: `"%1이(가) 공격합니다!"` | `"%1이(가) 공격합니다!"` |
| message2 | string | 사용 메시지 2 | `""` |
| messageType | int | 메시지 표시 유형 | `1` |
| mpCost | int | 소모 MP (0~9999) | `0` |
| name | string | 스킬명 | `"공격"` |
| note | string | 메모 | `""` |
| occasion | int | 사용 상황: 0=항상, 1=전투만, 2=메뉴만, 3=사용불가 | `1` |
| repeats | int | 반복 횟수 (1~9) | `1` |
| requiredWtypeId1 | int | 필요 무기유형 1 (0=없음, 0~12) | `0` |
| requiredWtypeId2 | int | 필요 무기유형 2 (0=없음, 0~12) | `0` |
| scope | int | 효과 범위 (→ [scope 값](#scope-효과-범위)) | `1` |
| speed | int | 속도 보정 (0~2000) | `0` |
| stypeId | int | 스킬 유형 (0~2): 0=없음(기본), 1=마법, 2=필살기 | `0` |
| successRate | int | 성공률 (1~100%) | `100` |
| tpCost | int | 소모 TP (0~100) | `0` |
| tpGain | int | 사용 시 획득 TP (0~100) | `5` |


---

## Items.json

소비 아이템 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 아이템명 | `"포션"` |
| description | string | 설명 (줄바꿈: `\n`) | `"HP를 100 회복한다."` |
| iconIndex | int | 아이콘 번호 (IconSet 이미지 내 인덱스) | `64` |
| itypeId | int | 아이템 유형 (1~4): 1=상비 아이템, 2=핵심 아이템, 3=숨겨진 아이템A, 4=숨겨진 아이템B | `1` |
| price | int | 상점 가격 (0~999999) | `50` |
| consumable | bool | 소모품 여부 (사용 시 소멸) | `true` |
| scope | int | 효과 범위 (→ [scope 값](#scope-효과-범위)) | `7` |
| occasion | int | 사용 가능 상황: 0=항상, 1=전투만, 2=메뉴만, 3=사용불가 | `0` |
| speed | int | 속도 보정값 (0~2000) | `0` |
| successRate | int | 성공률 (1~100%) | `100` |
| repeats | int | 반복 횟수 (1~9) | `1` |
| tpGain | int | 사용 시 획득 TP (0~100) | `0` |
| hitType | int | 명중 유형: 0=확정, 1=물리, 2=마법 | `0` |
| animationId | int | 사용 시 애니메이션 ID (-1~120, -1=없음) | `0` |
| damage | Damage | 데미지 설정 (→ [Damage 구조](#damage-구조)) | `{}` |
| effects | Effect[] | 효과 배열 (→ [Effect 구조](#effect-구조)) | `[]` |
| note | string | 메모 | `""` |

---

## Weapons.json

무기 장비 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 무기명 | `"단검"` |
| description | string | 설명 | `"가벼운 단검"` |
| iconIndex | int | 아이콘 번호 | `97` |
| price | int | 가격 | `300` |
| wtypeId | int | 무기 유형 ID (0~6, System.weaponTypes 참조) | `2` |
| etypeId | int | 장비 유형 (0~5): 항상 1=무기 | `1` |
| params | int[8] | 능력치 보정 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]. 기본값: `[0,0,8,0,0,0,0,0]` | `[0,0,10,0,0,0,0,0]` |
| traits | Trait[] | 특성 배열 | (배열) |
| animationId | int | 공격 시 애니메이션 ID (-1~120) | `6` |
| note | string | 메모 | `""` |

### 무기 유형 (wtypeId) 기본값
| ID | 유형 |
|----|------|
| 0 | 없음 |
| 1 | 단검 |
| 2 | 검 |
| 3 | 철퇴 |
| 4 | 도끼 |
| 5 | 채찍 |
| 6 | 지팡이 |

> 스키마 유효 범위: 0~6. 7 이상은 허용하지 않음.

---

## Armors.json

방어구 장비 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 방어구명 | `"가죽 갑옷"` |
| description | string | 설명 | `""` |
| iconIndex | int | 아이콘 번호 | `135` |
| price | int | 가격 | `100` |
| atypeId | int | 방어구 유형 ID (0~6, System.armorTypes 참조) | `1` |
| etypeId | int | 장비 슬롯 (0~5): 2=방패, 3=머리, 4=몸, 5=장신구 | `4` |
| params | int[8] | 능력치 보정 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]. 기본값: `[0,0,8,0,0,0,0,0]` | `[0,0,0,5,0,0,0,0]` |
| traits | Trait[] | 특성 배열 | (배열) |
| note | string | 메모 | `""` |

### 장비 슬롯 (etypeId)
| ID | 슬롯 |
|----|------|
| 1 | 무기 |
| 2 | 방패 |
| 3 | 머리 |
| 4 | 몸 |
| 5 | 장신구 |

---

## Enemies.json

전투에서 만나는 적 캐릭터 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 적 이름 | `"고블린"` |
| battlerName | string | 전투 이미지 파일명 (img/enemies/ 또는 img/sv_enemies/) | `"Goblin"` |
| battlerHue | int | 이미지 색조 변경 (0~360) | `0` |
| params | int[8] | 능력치 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK] | `[100, 50, 15, 10, 12, 8, 10, 10]` |
| exp | int | 처치 시 획득 경험치 | `10` |
| gold | int | 처치 시 획득 골드 | `5` |
| dropItems | DropItem[3] | 드롭 아이템 (항상 3개 슬롯) | (배열) |
| actions | Action[] | 행동 패턴 | (배열) |
| traits | Trait[] | 특성 배열 | (배열) |
| note | string | 메모 | `""` |

### params 인덱스 (적/캐릭터 공통)
| 인덱스 | 약어 | 능력치 |
|--------|------|--------|
| 0 | MHP | 최대 HP |
| 1 | MMP | 최대 MP |
| 2 | ATK | 공격력 |
| 3 | DEF | 방어력 |
| 4 | MAT | 마법 공격력 |
| 5 | MDF | 마법 방어력 |
| 6 | AGI | 민첩성 |
| 7 | LUK | 운 |

### DropItem 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| kind | int | 0=없음, 1=아이템, 2=무기, 3=방어구 |
| dataId | int | 해당 종류 파일의 ID |
| denominator | int | 드롭 확률 1/N (N값, 1~999) |

### Action 구조 (적 행동 패턴)
| 필드명 | 타입 | 설명 |
|--------|------|------|
| skillId | int | 사용할 스킬 ID |
| conditionType | int | 조건 유형 (0=항상, 1=턴, 2=HP, 3=MP, 4=스테이트, 5=파티레벨, 6=스위치) |
| conditionParam1 | int | 조건 파라미터 1 |
| conditionParam2 | int | 조건 파라미터 2 |
| rating | int | 행동 우선도 (1~9, 높을수록 자주) |

---

## Troops.json

적 그룹 (전투 편성) 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 그룹명 | `"고블린*2"` |
| members | TroopMember[] | 구성원 목록 | (배열) |
| pages | TroopPage[] | 배틀 이벤트 페이지 | (배열) |

### TroopMember 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| enemyId | int | 적 ID (Enemies.json 참조, 0 이상) |
| x | int | 전투 화면 X 좌표 |
| y | int | 전투 화면 Y 좌표 |
| hidden | bool | 등장 시 숨김 여부 (true=반투명 상태로 등장) |

### TroopPage 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| conditions | TroopPageCondition | 실행 조건 |
| list | EventCommand[] | 이벤트 커맨드 리스트 |
| span | int | 간격: 0=전투, 1=턴, 2=모멘트 (0~2) |

### TroopPageCondition 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| turnEnding | bool | '순번 종료' 조건 활성화 여부 |
| turnValid | bool | '순번' 조건 활성화 여부 |
| turnA | int | 조건 턴 A (0 이상) |
| turnB | int | 조건 턴 B (0 이상) |
| enemyValid | bool | '적' 조건 활성화 여부 |
| enemyIndex | int | 조건 적 인덱스 (0 이상) |
| enemyHp | int | 조건 적 HP 비율 (0~100%) |
| actorValid | bool | '액터' 조건 활성화 여부 |
| actorId | int | 조건 액터 ID (0 이상) |
| actorHp | int | 조건 액터 HP 비율 (0~100%) |
| switchValid | bool | 스위치 조건 활성화 여부 |
| switchId | int | 조건 스위치 ID (0 이상) |

---

## States.json

상태이상(버프/디버프) 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID (1=전투불능) | `1` |
| name | string | 상태명 | `"전투 불능"` |
| iconIndex | int | 아이콘 번호 | `1` |
| priority | int | 표시 우선순위 (0~100, 높을수록 우선) | `100` |
| restriction | int | 행동 제한: 0=없음, 1=적공격, 2=아무나, 3=아군공격, 4=행동불가 | `4` |
| removeAtBattleEnd | bool | 전투 종료 시 해제 | `false` |
| removeByRestriction | bool | 행동 제한 시 해제 | `false` |
| autoRemovalTiming | int | 자동 해제: 0=없음, 1=행동종료후, 2=턴종료후 (0~2) | `0` |
| minTurns | int | 최소 지속 턴 (0~9999) | `1` |
| maxTurns | int | 최대 지속 턴 (0~9999) | `1` |
| removeByDamage | bool | 피해 시 해제 여부 | `false` |
| chanceByDamage | int | 피해 시 해제 확률 (0~100%) | `100` |
| removeByWalking | bool | 걸을 때 해제 여부 | `false` |
| stepsToRemove | int | 해제까지 걸음 수 (1~9999) | `100` |
| releaseByDamage | bool | 피해로 인한 해제 여부 (removeByDamage와 별개 필드) | `false` |
| message1 | string | 부여 메시지 (아군) | `"%1이(가) 쓰러졌습니다!"` |
| message2 | string | 부여 메시지 (적) | `"%1이(가) 죽었습니다!"` |
| message3 | string | 지속 중 메시지 | `""` |
| message4 | string | 해제 메시지 | `"%1이(가) 부활합니다!"` |
| messageType | int | 메시지 표시 유형 | `1` |
| motion | int | SV 전투 모션 (0=walk, 1=wait, 2=chant, 3=dead 등) | `3` |
| overlay | int | 오버레이 표시 (0=없음, 1~10=상태 오버레이) | `0` |
| traits | Trait[] | 특성 배열 | (배열) |
| note | string | 메모 | `""` |

---

## Animations.json

전투/이벤트 애니메이션 효과 정의.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 애니메이션 이름 (변경 가능) | `"물리 타격"` |
| effectName | string | Effekseer 이펙트 파일명 (effects/) | `"HitPhysical"` |
| displayType | int | 표시 유형 | `0` |
| flashTimings | FlashTiming[] | 플래시 타이밍 | (배열) |
| soundTimings | SoundTiming[] | 사운드 타이밍 | (배열) |
| offsetX | int | X 오프셋 | `0` |
| offsetY | int | Y 오프셋 | `0` |
| rotation | Rotation | 회전 {x, y, z} | `{x:0, y:0, z:0}` |
| scale | int | 스케일 (10~1000%) | `50` |
| speed | int | 재생 속도 (10~1000%) | `100` |

### FlashTiming 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| frame | int | 프레임 번호 (0 이상) |
| duration | int | 지속 시간 (프레임, 0 이상) |
| color | int[4] | [R, G, B, 강도] (기본값: [255, 255, 255, 255]) |

### SoundTiming 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| frame | int | 프레임 번호 (0 이상) |
| se | SE | 효과음 설정 |

### SE 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| name | string | 효과음 파일명 |
| pan | int | PAN (-100~100) |
| pitch | int | PITCH (50~150) |
| volume | int | VOLUME (0~100) |

---

## Tilesets.json

타일셋 정의. 맵의 tilesetId로 참조됨.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 타일셋 이름 | `"세계"` |
| mode | int | 모드: 0=필드, 1=지역 | `0` |
| tilesetNames | string[9] | 타일셋 이미지 파일명 [A1, A2, A3, A4, A5, B, C, D, E] | (배열) |
| flags | int[] | 타일별 통행/속성 플래그 (길이=8192) | (배열) |
| note | string | 메모 | `""` |

### tilesetNames 인덱스
| 인덱스 | 이름 | 용도 |
|--------|------|------|
| 0 | A1 | 애니메이션 (물, 폭포) |
| 1 | A2 | 지면 |
| 2 | A3 | 건물 외벽 |
| 3 | A4 | 벽 상단 |
| 4 | A5 | 바닥 |
| 5 | B | 장식 B |
| 6 | C | 장식 C |
| 7 | D | 장식 D |
| 8 | E | 장식 E |

---

## CommonEvents.json

공용 이벤트 (맵 이벤트와 달리 전역으로 실행 가능).

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 고유 ID | `1` |
| name | string | 이벤트명 | `"날씨 변경"` |
| trigger | int | 트리거: 0=없음(호출만), 1=자동실행, 2=병렬처리 | `0` |
| switchId | int | 트리거 스위치 ID (자동/병렬 시 이 스위치가 ON이면 실행) | `1` |
| list | Command[] | 이벤트 커맨드 리스트 | (배열) |

---

## System.json

게임 전체 설정. 딕셔너리 구조 (배열 아님).

### 핵심 설정

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| gameTitle | string | 게임 제목 | `"용사의 모험"` |
| locale | string | 로케일 | `"ko_KR"` |
| startMapId | int | 시작 맵 ID | `8` |
| startX | int | 시작 X 좌표 | `8` |
| startY | int | 시작 Y 좌표 | `6` |
| partyMembers | int[] | 초기 파티 멤버 Actor ID 배열 | `[1, 2, 3, 4]` |
| currencyUnit | string | 화폐 단위 | `"G"` |
| versionId | int | 프로젝트 버전 ID | `47951809` |

### 유형 정의 (이름 배열)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| elements | string[] | 속성 이름 배열 (인덱스=속성ID) |
| equipTypes | string[] | 장비 유형 이름 |
| skillTypes | string[] | 스킬 유형 이름 |
| weaponTypes | string[] | 무기 유형 이름 |
| armorTypes | string[] | 방어구 유형 이름 |
| switches | string[] | 스위치 이름 (인덱스=스위치ID) |
| variables | string[] | 변수 이름 (인덱스=변수ID) |

### BGM/ME/SE 설정

| 필드명 | 타입 | 설명 |
|--------|------|------|
| battleBgm | AudioFile | 전투 BGM |
| titleBgm | AudioFile | 타이틀 BGM |
| defeatMe | AudioFile | 전멸 ME |
| gameoverMe | AudioFile | 게임오버 ME |
| victoryMe | AudioFile | 승리 ME |
| sounds | AudioFile[24] | 시스템 SE [커서, 확인, 취소, 부저, 장비, 저장, 로드, ...] |

### 이미지 설정

| 필드명 | 타입 | 설명 |
|--------|------|------|
| title1Name | string | 타이틀 배경 이미지 (img/titles1/) |
| title2Name | string | 타이틀 프레임 이미지 (img/titles2/) |
| battleback1Name | string | 전투 배경 바닥 (img/battlebacks1/) |
| battleback2Name | string | 전투 배경 벽 (img/battlebacks2/) |
| battlerName | string | 적 전투 이미지 |
| battlerHue | int | 적 색조 |

### 옵션 플래그

| 필드명 | 타입 | 설명 | 기본값 |
|--------|------|------|--------|
| optDisplayTp | bool | TP 게이지 표시 | true |
| optExtraExp | bool | 예비 멤버 경험치 획득 | false |
| optFloorDeath | bool | 바닥 데미지로 전멸 가능 | false |
| optFollowers | bool | 대열 걷기 (파티원 따라다님) | true |
| optSideView | bool | 사이드뷰 전투 | false |
| optSlipDeath | bool | 슬립 데미지로 전멸 가능 | false |
| optTransparent | bool | 투명 상태로 시작 | true |
| optDrawTitle | bool | 타이틀 화면 표시 | true |
| optAutosave | bool | 자동 저장 | true |
| optKeyItemsNumber | bool | 핵심 아이템 소지 수 표시 | false |
| optMessageSkip | bool | 메시지 스킵 허용 | true |
| optSplashScreen | bool | 스플래시 화면 | false |

### 탈것 설정

| 필드명 | 타입 | 설명 |
|--------|------|------|
| boat | Vehicle | 보트 설정 |
| ship | Vehicle | 배 설정 |
| airship | Vehicle | 비행선 설정 |

### 기타

| 필드명 | 타입 | 설명 |
|--------|------|------|
| battleSystem | int | 전투 시스템 유형 |
| attackMotions | array | 공격 모션 설정 |
| editMapId | int | 에디터 마지막 편집 맵 |
| testBattlers | array | 테스트 전투 파티 |
| testTroopId | int | 테스트 전투 적 그룹 ID |
| terms | object | 용어 설정 {basic, commands, params, messages} |
| windowTone | int[4] | 윈도우 색조 [R, G, B, Gray] |
| titleCommandWindow | object | 타이틀 커맨드 창 설정 {background, offsetX, offsetY} |
| menuCommands | bool[] | 메뉴 커맨드 표시 설정 |
| magicSkills | int[] | 마법 스킬 유형 ID 배열 |
| advanced | object | 고급 설정 {gameId, screenWidth, screenHeight, uiAreaWidth, uiAreaHeight, ...} |
| editor | object | 에디터 설정 {messageWidth1, messageWidth2, jsonFormatLevel} |
| tileSize | int | 타일 크기 (px) |
| faceSize | int | 얼굴 이미지 크기 (px) |
| iconSize | int | 아이콘 크기 (px) |
| itemCategories | bool[] | 아이템 카테고리 표시 설정 |

---

## MapInfos.json

맵 목록/트리 구조 관리. 에디터의 맵 트리와 대응.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 맵 ID (Map{id:03d}.json과 대응) | `1` |
| name | string | 맵 표시 이름 | `"MAP001"` |
| parentId | int | 부모 맵 ID (0=최상위) | `0` |
| order | int | 트리 정렬 순서 | `2` |
| expanded | bool | 에디터에서 트리 노드 펼침 여부 | `true` |
| scrollX | int | 에디터 스크롤 X 위치 | `816` |
| scrollY | int | 에디터 스크롤 Y 위치 | `624` |

---

## MapXXX.json

개별 맵 데이터. 파일명은 `Map001.json`, `Map002.json` 등.

### 맵 기본 속성

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| displayName | string | 맵 진입 시 표시 이름 (빈 문자열=표시안함) | `"마을"` |
| width | int | 가로 타일 수 | `17` |
| height | int | 세로 타일 수 | `13` |
| tilesetId | int | 타일셋 ID (Tilesets.json 참조) | `1` |
| scrollType | int | 스크롤: 0=안함, 1=세로루프, 2=가로루프, 3=양방향 | `0` |
| data | int[] | 타일 데이터 (길이 = width * height * 6) | (대형 배열) |
| events | (Event\|null)[] | 이벤트 배열. 인덱스 0=null, 인덱스=이벤트ID | (배열) |
| note | string | 메모 | `""` |

### 맵 음악/배경

| 필드명 | 타입 | 설명 |
|--------|------|------|
| autoplayBgm | bool | BGM 자동 재생 |
| autoplayBgs | bool | BGS 자동 재생 |
| bgm | AudioFile | 맵 BGM {name, volume, pitch, pan} |
| bgs | AudioFile | 맵 BGS {name, volume, pitch, pan} |

### 인카운터 설정

| 필드명 | 타입 | 설명 |
|--------|------|------|
| encounterList | Encounter[] | 랜덤 인카운터 설정 |
| encounterStep | int | 인카운터 평균 보행수 (기본 30) |

### 전투 배경

| 필드명 | 타입 | 설명 |
|--------|------|------|
| specifyBattleback | bool | 전투배경 개별 지정 여부 |
| battleback1Name | string | 전투배경 바닥 이미지 |
| battleback2Name | string | 전투배경 벽 이미지 |

### 원경(Parallax)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| parallaxName | string | 원경 이미지 파일명 (img/parallaxes/) |
| parallaxLoopX | bool | X축 루프 |
| parallaxLoopY | bool | Y축 루프 |
| parallaxSx | int | X 스크롤 속도 |
| parallaxSy | int | Y 스크롤 속도 |
| parallaxShow | bool | 에디터 원경 표시 |

### 기타

| 필드명 | 타입 | 설명 |
|--------|------|------|
| disableDashing | bool | 대시 금지 |

### Encounter 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| troopId | int | 적 그룹 ID (Troops.json 참조) |
| weight | int | 출현 가중치 |
| regionSet | int[] | 출현 리전 ID 배열 |

---

## 맵 이벤트 (Event) 구조

맵의 `events` 배열 내 각 이벤트 객체.

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | int | 이벤트 ID (배열 인덱스와 동일) | `1` |
| name | string | 이벤트 이름 | `"마을 주민"` |
| x | int | 맵 X 좌표 (타일 단위) | `10` |
| y | int | 맵 Y 좌표 (타일 단위) | `8` |
| pages | EventPage[] | 이벤트 페이지 배열 (조건별 동작) | (배열) |
| note | string | 메모 | `""` |

### EventPage 구조

| 필드명 | 타입 | 설명 |
|--------|------|------|
| conditions | PageCondition | 이 페이지 활성화 조건 |
| image | EventImage | 이벤트 외형 |
| list | Command[] | 이벤트 커맨드 리스트 |
| moveType | int | 이동 유형: 0=고정, 1=랜덤, 2=접근, 3=커스텀 |
| moveSpeed | int | 이동 속도 (1~6, 기본 3=표준) |
| moveFrequency | int | 이동 빈도 (1~5, 기본 3=보통) |
| moveRoute | MoveRoute | 커스텀 이동 경로 |
| priorityType | int | 표시 우선: 0=캐릭터 아래, 1=캐릭터와 같음, 2=캐릭터 위 |
| trigger | int | 트리거: 0=확인키, 1=플레이어접촉, 2=이벤트접촉, 3=자동실행, 4=병렬처리 |
| walkAnime | bool | 걷기 애니메이션 |
| stepAnime | bool | 제자리 걸음 |
| directionFix | bool | 방향 고정 |
| through | bool | 투명 통과 |

### PageCondition 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| actorValid | bool | 액터 조건 활성화 |
| actorId | int | 조건 액터 ID |
| itemValid | bool | 아이템 조건 활성화 |
| itemId | int | 조건 아이템 ID |
| selfSwitchValid | bool | 셀프 스위치 조건 활성화 |
| selfSwitchCh | string | 셀프 스위치 채널 ("A"~"D") |
| switch1Valid | bool | 스위치 1 조건 활성화 |
| switch1Id | int | 스위치 1 ID |
| switch2Valid | bool | 스위치 2 조건 활성화 |
| switch2Id | int | 스위치 2 ID |
| variableValid | bool | 변수 조건 활성화 |
| variableId | int | 조건 변수 ID |
| variableValue | int | 조건 변수 값 (이상) |

### EventImage 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| tileId | int | 타일 ID (0=캐릭터 이미지 사용) |
| characterName | string | 캐릭터 이미지 파일명 ("People1", "Actor1" 등) |
| characterIndex | int | 시트 내 인덱스 (0~7) |
| direction | int | 방향: 2=아래, 4=왼쪽, 6=오른쪽, 8=위 |
| pattern | int | 패턴 (0~2, 기본 1=중앙) |

### MoveRoute 구조
| 필드명 | 타입 | 설명 |
|--------|------|------|
| repeat | bool | 반복 실행 |
| skippable | bool | 이동 불가 시 스킵 |
| wait | bool | 완료까지 대기 |
| list | MoveCommand[] | 이동 커맨드 [{code, parameters}] |

---

## 공통 서브구조

### Trait

모든 데이터에서 공통으로 사용되는 특성 구조.

| 필드명 | 타입 | 설명 |
|--------|------|------|
| code | int | 특성 코드 |
| dataId | int | 데이터 ID |
| value | float | 값 |

주요 특성 코드: #여기여기여기여기 업데이트
| code | 의미 | dataId | value |
|------|------|--------|-------|
| 11 | 속성 내성 | 속성ID | 내성률 (1.0=100%) |
| 12 | 여기 | 여기 | 여기 |
| 13 | 상태 내성 | 상태ID | 내성률 |
| 21 | 능력치 보정 | 능력치인덱스(0~7) | 보정률 |
| 22 | 추가 능력치 | 0=명중, 1=회피, ... | 보정값 |
| 31 | 공격 시 속성 | 속성ID | - |
| 32 | 공격 시 상태 | 상태ID | 부여율 |
| 33 | 공격 속도 보정 | - | 보정값 |
| 34 | 공격 추가 횟수 | - | 추가횟수 |
| 41 | 스킬 유형 추가 | 스킬유형ID | - |
| 42 | 스킬 유형 봉인 | 스킬유형ID | - |
| 43 | 스킬 추가 | 스킬ID | - |
| 44 | 스킬 봉인 | 스킬ID | - |
| 51 | 무기 유형 장비 | 무기유형ID | - |
| 52 | 방어구 유형 장비 | 방어구유형ID | - |
| 53 | 장비 고정 | 장비유형ID | - |
| 54 | 장비 봉인 | 장비유형ID | - |
| 55 | 이중 장비 슬롯 | 장비유형ID | - |
| 61 | 추가 행동 | - | 확률 |
| 62 | 특수 플래그 | 0=자동전투, 1=방어, 2=대체방어, 3=TP지속 | - |
| 63 | 소멸 효과 | 0=사라짐, 1=보스소멸 | - |
| 64 | 파티 능력 | 0=인카운터반감, 1=인카운터무효, 2=기습무효, 3=선제확률UP, 4=획득골드2배, 5=아이템드롭2배 | - |

### Damage 구조

스킬/아이템의 데미지 설정.

| 필드명 | 타입 | 설명 |
|--------|------|------|
| critical | bool | 크리티컬 가능 여부 |
| elementId | int | 속성 ID (0~10): 0=없음, 1=물리적, 2=불, 3=얼음, 4=천둥, 5=물, 6=흙, 7=바람, 8=빛, 9=어둠, 10 이상=없음으로 처리 |
| formula | string | 데미지 계산식 (`a.atk * 4 - b.def * 2`) |
| type | int | 0=없음, 1=HP피해, 2=MP피해, 3=HP회복, 4=MP회복, 5=HP흡수, 6=MP흡수 |
| variance | int | 분산도 (%) |

### Effect 구조

스킬/아이템의 효과.

| 필드명 | 타입 | 설명 |
|--------|------|------|
| code | int | 효과 코드 |
| dataId | int | 데이터 ID |
| value1 | float | 값 1 |
| value2 | float | 값 2 |

주요 효과 코드:
| code | 효과 | dataId | value1 | value2 |
|------|------|--------|--------|--------|
| 11 | HP 회복 | - | 비율 | 고정값 |
| 12 | MP 회복 | - | 비율 | 고정값 |
| 13 | TP 획득 | - | 값 | - |
| 21 | 상태 부여 | 상태ID | 확률 | - |
| 22 | 상태 해제 | 상태ID | 확률 | - |
| 31 | 버프 | 능력치(0~7) | 턴 수 | - |
| 32 | 디버프 | 능력치(0~7) | 턴 수 | - |
| 33 | 버프 해제 | 능력치(0~7) | 확률 | - |
| 34 | 디버프 해제 | 능력치(0~7) | 확률 | - |
| 41 | 특수 효과 | 0=도주 | - | - |
| 42 | 성장 | 능력치(0~7) | 값 | - |
| 43 | 스킬 습득 | 스킬ID | - | - |
| 44 | 공용이벤트 | 이벤트ID | - | - |

### AudioFile 구조

BGM, BGS, ME, SE 등 모든 음원 설정.

| 필드명 | 타입 | 설명 | 기본값 |
|--------|------|------|--------|
| name | string | 오디오 파일명 (확장자 없이) | `""` |
| volume | int | 볼륨 (0~100) | `90` |
| pitch | int | 피치 (50~150) | `100` |
| pan | int | 패닝 (-100~100, 0=중앙) | `0` |

### scope (효과 범위)

스킬/아이템의 scope 값. ##여기

| 값 | 대상 |
|----|------|
| 0 | 없음 |
| 1 | 고정 적 1체 |
| 2 | 적 전체 |
| 3 | 랜덤 적 1체 |
| 4 | 랜덤 적 2체 |
| 5 | 랜덤 적 3체 |
| 6 | 랜덤 적 4체 |
| 7 | 고정 아군 1체 생존 시 |
| 8 | 아군 전체 생존 시 |
| 9 | 고정 아군 1체 전투불능 시 |
| 10 | 아군 전체 전투불능 시 |
| 11 | 사용자 자신 |
| 12 | 고정 아군 1체 조건 없음 |
| 13 | 아군 전체 조건 없음 |
| 14 | 모두(적&아군 전체) |

### 이벤트 커맨드 (Command) 주요 코드

| code | 커맨드 | parameters |
|------|--------|------------|
| 0 | 이벤트 종료 | `[]` (항상 마지막에 필수) |
| 101 | 텍스트 표시 설정 | `[faceName, faceIndex, background, positionType]` |
| 401 | 텍스트 내용 | `["대화 내용"]` (101 뒤에 사용) |
| 102 | 선택지 표시 | `[["선택1","선택2",...], cancelType, defaultType, positionType, background]` |
| 402 | 선택지 분기 | `[index, "선택텍스트"]` |
| 108 | 주석 | `["주석 내용"]` |
| 111 | 조건 분기 | (조건에 따라 다양) |
| 117 | 공용 이벤트 | `[commonEventId]` |
| 121 | 스위치 조작 | `[startId, endId, value(0=OFF,1=ON)]` |
| 122 | 변수 조작 | `[startId, endId, operationType, operand, ...]` |
| 125 | 골드 변경 | `[operation(0=증가,1=감소), operandType, operand]` |
| 126 | 아이템 변경 | `[itemId, operation, operandType, operand]` |
| 127 | 무기 변경 | `[weaponId, operation, operandType, operand, includeEquipment]` |
| 128 | 방어구 변경 | `[armorId, operation, operandType, operand, includeEquipment]` |
| 129 | 파티 변경 | `[actorId, operation(0=추가,1=제거), initialize]` |
| 201 | 장소 이동 | `[designationType(0=직접), mapId, x, y, direction, fadeType]` |
| 205 | 이동 경로 | `[characterId(-1=플레이어,0=이벤트자신), moveRoute]` |
| 230 | 대기 | `[duration(프레임)]` |
| 231 | 그림 표시 | `[pictureId, name, origin, designationType, x, y, scaleX, scaleY, opacity, blendMode]` |
| 241 | BGM 재생 | `[{name, volume, pitch, pan}]` |
| 245 | BGS 재생 | `[{name, volume, pitch, pan}]` |
| 249 | ME 재생 | `[{name, volume, pitch, pan}]` |
| 250 | SE 재생 | `[{name, volume, pitch, pan}]` |
| 301 | 전투 처리 | `[troopDesignation, troopId, canEscape, canLose]` |
| 302 | 상점 처리 | `[goodsType(0=아이템,1=무기,2=방어구), itemId, priceType, price]` |
| 303 | 이름 입력 | `[actorId, maxLength]` |
| 311 | HP 변경 | `[isVariable, actorId, operation, operandType, operand, allowDeath]` |
| 312 | MP 변경 | `[isVariable, actorId, operation, operandType, operand]` |
| 313 | 상태 변경 | `[isVariable, actorId, operation(0=부여,1=해제), stateId]` |
| 314 | 전회복 | `[actorId]` |
| 315 | EXP 변경 | `[isVariable, actorId, operation, operandType, operand, showLevelUp]` |
| 316 | 레벨 변경 | `[isVariable, actorId, operation, operandType, operand, showLevelUp]` |
| 320 | 닉네임 변경 | `[actorId, nickname]` |
| 322 | 클래스 변경 | `[actorId, classId, keepExp]` |
| 351 | 메뉴 화면 열기 | `[]` |
| 352 | 세이브 화면 열기 | `[]` |
| 353 | 게임 오버 | `[]` |
| 354 | 타이틀로 | `[]` |
| 355 | 스크립트 | `["JavaScript 코드"]` |
| 655 | 스크립트 (계속) | `["JavaScript 코드 계속"]` |
