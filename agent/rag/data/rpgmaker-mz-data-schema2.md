## Actors

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `classId` | `Classes` | `index_ref` | `Classes`의 해당 인덱스 값 불러옴 |
| `equips` | `Classes` | `trait_ref` | `Classes.traits` 중 `{"code":51~52,"dataId":n,"value":0}` 형태의 장비 정의를 가져옴 |
| `traits[*]` | `?` | `pending` | traits 상세 규칙 정의 필요 |

## Classes

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `learnings[].skillId` | `Skills` | `index_ref` | `Skills`의 해당 인덱스 값 불러옴 |
| `traits[code=51].dataId` | `Weapons` | `index_ref` | `Weapons`의 해당 인덱스 값 불러옴 |
| `traits[code=52].dataId` | `Armors` | `index_ref` | `Armors`의 해당 인덱스 값 불러옴 |

## Skills

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `animationId` | `Animations` | `index_ref` | `Animations`의 해당 인덱스 값 불러옴 |
| `damage.elementId` | `System.elements` | `index_ref` | `System.elements`의 해당 인덱스 값 불러옴 |
| `effects[code=21].dataId` | `States` | `index_ref` | `States`의 해당 인덱스 값 불러옴 |
| `requiredWtypeId1` | `System.weaponTypes` | `index_ref` | `System.weaponTypes`의 해당 인덱스 값 불러옴 |
| `requiredWtypeId2` | `System.weaponTypes` | `index_ref` | `System.weaponTypes`의 해당 인덱스 값 불러옴 |
| `stypeId` | `System.skillTypes` | `index_ref` | `System.skillTypes`의 해당 인덱스 값 불러옴 |

## Items

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `animationId` | `Animations` | `index_ref` | `Animations`의 해당 인덱스 값 불러옴 |
| `damage.elementId` | `System.elements` | `index_ref` | `System.elements`의 해당 인덱스 값 불러옴 |

## Weapons

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `animationId` | `Animations` | `index_ref` | `Animations`의 해당 인덱스 값 불러옴 |
| `etypeId` | `System.equipTypes` | `index_ref` | `System.equipTypes`의 해당 인덱스 값 불러옴 |
| `wtypeId` | `System.weaponTypes` | `index_ref` | `System.weaponTypes`의 해당 인덱스 값 불러옴 |

## Armors

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `atypeId` | `System.armorTypes` | `index_ref` | `System.armorTypes`의 해당 인덱스 값 불러옴 |
| `etypeId` | `System.equipTypes` | `index_ref` | `System.equipTypes`의 해당 인덱스 값 불러옴 |

## Enemies

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `actions[].skillId` | `Skills` | `index_ref` | `Skills`의 해당 인덱스 값 불러옴 |
| `dropItems[kind=1].dataId` | `Items` | `index_ref` | `Items`의 해당 인덱스 값 불러옴 |

## Troops

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `members[].enemyId` | `Enemies` | `index_ref` | `Enemies`의 해당 인덱스 값 불러옴 |
| `(추가 규칙 미정)` |  |  | 아직 정의 안 됨 |

## States

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `(없음)` |  |  | 다른 JSON을 참조하지 않음 |

## Animations

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `(없음)` |  |  | 다른 JSON을 참조하지 않음 |

## System

| 필드 | 참조 대상 | 참조 방식 | 설명 |
| --- | --- | --- | --- |
| `partyMembers[]` | `Actors` | `index_ref` | 예: `[1,4,6,7]` 형태로 `Actors` 인덱스 값 불러옴 |
| `testBattlers[].actorId` | `Actors` | `index_ref` | `Actors`의 해당 인덱스 값 불러옴 |
| `testBattlers` | `Classes` | `context_ref` | 네 정의 기준으로 관련 값 함께 참조 |
| `testBattlers[].equips[]` | `Weapons`, `Armors` | `index_ref` | 장비 인덱스 값 불러옴 |
| `testTroopId` | `Troops` | `index_ref` | `Troops`의 해당 인덱스 값 불러옴 |
