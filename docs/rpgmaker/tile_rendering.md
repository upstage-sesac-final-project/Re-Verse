# RPG Maker MZ 타일 렌더링 로직

> 이 문서는 `rmmz_core.js` 엔진 소스를 역분석하여 확인한 실제 렌더링 공식을 기술한다.
> 프론트엔드 Map Viewer(`MapViewer.jsx`)에 구현되어 있으며, 백엔드/다른 클라이언트에서도 동일하게 적용할 수 있다.

---

## 1. 맵 데이터 구조

맵 JSON(`MapXXX.json`)의 `data` 필드는 **1차원 정수 배열**이다.

```
data.length = width × height × 6
```

| 레이어 인덱스 | 용도 | 값 범위 |
|---|---|---|
| 0~3 | 일반 타일 (tileId) | 0 이상 (0 = 빈 칸) |
| 4 | 그림자 (비트 플래그) | 0~15 |
| 5 | 리전 ID | 0~255 |

**레이어 내 좌표 → 배열 인덱스 변환:**

```
index = layer × (width × height) + y × width + x
```

---

## 2. 타일셋 이미지 구조

`Tilesets.json`의 `tilesetNames` 배열은 고정 순서로 9개 이미지를 참조한다.

| 배열 인덱스 | 타입 | tileId 범위 |
|---|---|---|
| 0 | A1 (애니메이션: 물, 폭포) | 2048~2815 |
| 1 | A2 (지면 오토타일) | 2816~4351 |
| 2 | A3 (지붕 오토타일) | 4352~5887 |
| 3 | A4 (벽 오토타일) | 5888~8191 |
| 4 | A5 (일반 타일) | 1536~2047 |
| 5 | B | 0~255 |
| 6 | C | 256~511 |
| 7 | D | 512~767 |
| 8 | E | 768~1023 |

---

## 3. tileId → 타일셋 이미지 내 좌표 공식

### 3-1. 오토타일 공통 (A1~A4): 전역 kind & shape

A1~A4 오토타일은 **모두 A1(2048)을 기준**으로 전역 kind를 계산한다.

```
globalKind = floor((tileId - 2048) / 48)
shape      = (tileId - 2048) % 48

tx = globalKind % 8
ty = floor(globalKind / 8)
```

- `shape`: 주변 타일과의 연결 패턴(0~47). tileId에 인코딩되어 있어 이웃 타일을 확인할 필요가 없다.
- `tx`, `ty`: 타일셋 시트 내 타일 그룹의 위치.

---

### 3-2. 오토타일 쿼터 피스 조합 방식

오토타일 1칸은 **24×24px 쿼터 피스 4개**를 조합해 48×48px 타일로 구성한다.

```
[0] 좌상  [1] 우상
[2] 좌하  [3] 우하
```

각 쿼터 피스의 소스 좌표:

```
srcX = (bx*2 + qsx) * 24
srcY = (by*2 + qsy) * 24
```

`bx`, `by`는 타일셋 내 블록 위치(아래 각 타입별 공식 참조),
`[qsx, qsy]`는 shape에 따른 **오토타일 테이블** 조회 결과.

---

### 3-3. 오토타일 테이블

연결 패턴(shape)에 따라 4개 쿼터 피스의 `[qsx, qsy]`를 반환한다.

**FLOOR_AUTOTILE_TABLE** (48종, A1/A2/A4 짝수행에 사용):
```
shape 0  → [[2,4],[1,4],[2,3],[1,3]]
shape 1  → [[2,0],[1,4],[2,3],[1,3]]
...
shape 47 → [[0,0],[1,0],[0,1],[1,1]]
```

**WALL_AUTOTILE_TABLE** (16종, A3/A4 홀수행에 사용):
```
shape 0  → [[2,2],[1,2],[2,1],[1,1]]
...
shape 15 → [[0,0],[3,0],[0,3],[3,3]]
```

**WATERFALL_AUTOTILE_TABLE** (4종, A1 폭포에 사용):
```
shape 0  → [[2,0],[1,0],[2,1],[1,1]]
...
shape 3  → [[0,0],[3,0],[0,1],[3,1]]
```

> 전체 테이블 값은 `MapViewer.jsx` 상단 상수 참조.

---

### 3-4. A1 (애니메이션 타일, tileId 2048~2815)

globalKind = 0~15, ty = 0~1.

| kind | bx | by | table |
|---|---|---|---|
| 0 | 0 | 0 | FLOOR |
| 1 | 0 | 3 | FLOOR |
| 2 | 6 | 0 | FLOOR |
| 3 | 6 | 3 | FLOOR |
| 4+ (짝수) | `floor(tx/4)*8` | `ty*6 + (floor(tx/2)%2)*3` | FLOOR |
| 4+ (홀수) | 위 bx + 6 | 위 by | WATERFALL |

---

### 3-5. A2 (지면 오토타일, tileId 2816~4351)

globalKind = 16~47, ty = 2~5.

```
bx = tx * 2
by = (ty - 2) * 3
table = FLOOR_AUTOTILE_TABLE
```

---

### 3-6. A3 (지붕 오토타일, tileId 4352~5887)

globalKind = 48~79, ty = 6~9.

```
bx = tx * 2
by = (ty - 6) * 2
table = WALL_AUTOTILE_TABLE
```

---

### 3-7. A4 (벽 오토타일, tileId 5888~8191)

globalKind = 80~127, ty = 10~15. 짝수 행은 바닥, 홀수 행은 벽면.

```
bx    = tx * 2
by    = floor((ty - 10) * 2.5 + (ty % 2 === 1 ? 0.5 : 0))
table = (ty % 2 === 1) ? WALL_AUTOTILE_TABLE : FLOOR_AUTOTILE_TABLE
```

**ty별 시트 내 y 위치 (24px 단위):**

| ty | by | table | srcY 시작 |
|---|---|---|---|
| 10 | 0 | FLOOR | 0px |
| 11 | 3 | WALL | 144px |
| 12 | 5 | FLOOR | 240px |
| 13 | 8 | WALL | 384px |
| 14 | 10 | FLOOR | 480px |
| 15 | 13 | WALL | 624px |

---

### 3-8. A5 (일반 타일, tileId 1536~2047)

오토타일 없이 48×48px 단일 이미지 복사.

```
sx = ((floor(tileId / 128) % 2) * 8 + (tileId % 8)) * 48
sy = (floor((tileId % 256) / 8) % 16) * 48
```

---

### 3-9. B~E 일반 타일 (tileId 0~1023)

```
setIndex = 5 + floor(tileId / 256)   // 이미지 배열 인덱스 (5=B, 6=C, 7=D, 8=E)
sx = ((floor(tileId / 128) % 2) * 8 + (tileId % 8)) * 48
sy = (floor((tileId % 256) / 8) % 16) * 48
```

시트 레이아웃: 왼쪽 8열(tileId 0~127) + 오른쪽 8열(tileId 128~255), 각 16행 = 768×768px.

---

## 4. 그림자 레이어 (레이어 4)

레이어 4의 값은 tileId가 아닌 **4비트 플래그**이다. 각 비트는 48×48px 타일의 4분면에 대응한다.

| 비트 | 값 | 위치 |
|---|---|---|
| 0 | 1 | 좌상 |
| 1 | 2 | 우상 |
| 2 | 4 | 좌하 |
| 3 | 8 | 우하 |

**렌더링:** 해당 분면에 `rgba(0,0,0,0.5)` 반투명 검정 사각형을 그린다.

```
if (flags & 1) fillRect(x,        y,        w/2, h/2)  // 좌상
if (flags & 2) fillRect(x + w/2,  y,        w/2, h/2)  // 우상
if (flags & 4) fillRect(x,        y + h/2,  w/2, h/2)  // 좌하
if (flags & 8) fillRect(x + w/2,  y + h/2,  w/2, h/2)  // 우하
```

---

## 5. 렌더링 순서 요약

```
1. 배경 fillRect (단색)
2. 레이어 0 → 타일 렌더링
3. 레이어 1 → 타일 렌더링
4. 레이어 2 → 타일 렌더링
5. 레이어 3 → 타일 렌더링
6. 레이어 4 → 그림자 렌더링 (비트 플래그)
7. 레이어 5 → 리전 (선택적, 숫자 표시)
```

---

## 6. 주요 상수

| 상수 | 값 | 설명 |
|---|---|---|
| TS | 48 | 타일 1칸 기본 크기(px) |
| QUARTER | 24 | 오토타일 쿼터 피스 크기(px) |
| A1_BASE | 2048 | 전역 kind 계산 기준 tileId |
| KINDS_PER_TYPE | 48 | 오토타일 1종당 tileId 수 |

---

## 7. 참고

- 공식 출처: `storage/games/game_001/js/rmmz_core.js` — `Tilemap._addAutotile`, `Tilemap._addNormalTile`, `Tilemap._addShadow`
- 구현 파일: `app/frontend/src/components/game/MapViewer.jsx`
