# 기존 게임 마이그레이션 가이드

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 목적

사용자가 이미 가진 RPG Maker MZ 프로젝트(수동 제작 또는 외부 생성)를
Re:Verse 시스템으로 가져와 **Incremental Edit** 또는 **Full Generation 부분 재생성**을
사용할 수 있게 한다.

---

## 마이그레이션이 필요한 경우

| 상황 | 설명 |
|------|------|
| 기존 수작업 프로젝트 가져오기 | 사용자가 RPG Maker MZ로 직접 만든 프로젝트 |
| Full Generation 이전 버전 가져오기 | Full Gen 기능 개발 전에 만들어진 게임 |
| 외부 도구 생성 프로젝트 | 다른 생성 도구로 만든 RPG Maker MZ 호환 프로젝트 |
| 테스트 픽스처 | 개발/테스트용 고정 프로젝트 투입 |

---

## 마이그레이션 제약

### 지원 범위

- RPG Maker MZ JSON 포맷 (`.json`) 전용
- 지원 파일: `Actors.json`, `Classes.json`, `Skills.json`, `Items.json`,
  `Weapons.json`, `Armors.json`, `Enemies.json`, `Troops.json`,
  `System.json`, `Map*.json`
- 지원 타일셋: 기본 타일셋 1(마을), 2(던전), 3(필드)

### 미지원 범위

- RPG Maker MV 포맷 (구조가 다름 — 별도 변환 필요)
- 플러그인 커맨드 (code 356)는 Incremental Edit 불가 (읽기만 가능)
- 커스텀 타일셋 (tilesetId ≥ 4): 경고 표시 후 허용

---

## 마이그레이션 흐름

```
사용자가 ZIP 업로드 (RPG Maker MZ 프로젝트)
    │
    ▼
1. 파일 검증 (validate_upload)
   └─ 필수 파일 존재 여부, JSON 파싱 가능 여부
    │
    ▼
2. 구조 분석 (analyze_project)
   └─ ID 범위, 맵 수, 이벤트 수, 타일셋 종류
    │
    ▼
3. game_files 저장 (store_game_files)
   └─ 파일별로 game_files 테이블에 INSERT
    │
    ▼
4. IdTable 재구성 (rebuild_id_table)
   └─ 기존 JSON에서 이름→ID 역매핑 추출
    │
    ▼
5. generations 레코드 생성 (create_import_record)
   └─ status='imported', source='user_upload'
    │
    ▼
완료 → Incremental Edit / 부분 재생성 사용 가능
```

---

## API 설계

### 업로드 엔드포인트

```http
POST /api/v1/games/{game_id}/import
Content-Type: multipart/form-data

Body:
  file: <ZIP 파일>
  overwrite: true | false   (기본 false — 기존 데이터 보호)
```

**응답 (202 Accepted)**:
```json
{
  "import_id": "uuid",
  "status": "processing",
  "message": "파일 분석 중..."
}
```

**응답 (200 OK — 완료)**:
```json
{
  "import_id": "uuid",
  "status": "completed",
  "summary": {
    "actors": 4,
    "skills": 15,
    "items": 20,
    "enemies": 8,
    "maps": 3,
    "events": 24
  },
  "warnings": [
    "커스텀 타일셋(tilesetId=5) 발견 — 맵 재생성 시 기본 타일셋으로 대체됩니다"
  ]
}
```

---

## 구현 상세

### 1. 파일 검증

```python
REQUIRED_FILES = {
    "Actors.json", "Classes.json", "Skills.json", "Items.json",
    "Weapons.json", "Armors.json", "Enemies.json", "Troops.json",
    "System.json",
}

def validate_upload(zip_path: str) -> ValidationResult:
    """ZIP 파일 기본 검증."""
    errors: list[str] = []
    warnings: list[str] = []

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        # 필수 파일 확인
        for req in REQUIRED_FILES:
            if not any(n.endswith(req) for n in names):
                errors.append(f"필수 파일 없음: {req}")
        # 맵 파일 확인
        maps = [n for n in names if re.match(r"Map\d{3}\.json$", n.split("/")[-1])]
        if not maps:
            warnings.append("Map*.json 파일이 없습니다 (맵 없는 프로젝트)")
        # 크기 확인
        total = sum(zf.getinfo(n).file_size for n in names)
        if total > 50 * 1024 * 1024:  # 50MB
            errors.append(f"파일 크기 초과: {total // 1024 // 1024}MB > 50MB")
        # JSON 파싱 가능 여부
        for req in REQUIRED_FILES:
            candidates = [n for n in names if n.endswith(req)]
            if candidates:
                try:
                    json.loads(zf.read(candidates[0]))
                except json.JSONDecodeError as e:
                    errors.append(f"{req} JSON 파싱 실패: {e}")

    return ValidationResult(errors=errors, warnings=warnings)
```

### 2. 구조 분석

```python
@dataclass
class ProjectSummary:
    actors:     int
    classes:    int
    skills:     int
    items:      int
    weapons:    int
    armors:     int
    enemies:    int
    troops:     int
    maps:       int
    total_events: int
    tileset_ids: list[int]
    has_custom_tilesets: bool

def analyze_project(files: dict[str, Any]) -> ProjectSummary:
    """파싱된 JSON 딕셔너리에서 프로젝트 규모 분석."""

    def count_non_null(data: list) -> int:
        return sum(1 for item in data if item is not None)

    tileset_ids = []
    total_events = 0
    for key, data in files.items():
        if re.match(r"Map\d{3}\.json$", key):
            tset = data.get("tilesetId", 1)
            if tset not in tileset_ids:
                tileset_ids.append(tset)
            # 이벤트 수 집계
            events = data.get("events", [])
            total_events += count_non_null(events)

    return ProjectSummary(
        actors=count_non_null(files.get("Actors.json", [])),
        classes=count_non_null(files.get("Classes.json", [])),
        skills=count_non_null(files.get("Skills.json", [])),
        items=count_non_null(files.get("Items.json", [])),
        weapons=count_non_null(files.get("Weapons.json", [])),
        armors=count_non_null(files.get("Armors.json", [])),
        enemies=count_non_null(files.get("Enemies.json", [])),
        troops=count_non_null(files.get("Troops.json", [])),
        maps=len([k for k in files if re.match(r"Map\d{3}\.json$", k)]),
        total_events=total_events,
        tileset_ids=sorted(tileset_ids),
        has_custom_tilesets=any(tid > 3 for tid in tileset_ids),
    )
```

### 3. game_files 저장

```python
async def store_game_files(
    game_id: str,
    files: dict[str, Any],
    db,
    overwrite: bool = False,
) -> None:
    """파싱된 JSON을 game_files 테이블에 저장."""
    if overwrite:
        await db.execute(
            "DELETE FROM game_files WHERE game_id = $1",
            game_id,
        )

    for filename, data in files.items():
        await db.execute(
            """
            INSERT INTO game_files (game_id, filename, content, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (game_id, filename) DO UPDATE
              SET content = EXCLUDED.content, updated_at = now()
            """,
            game_id, filename, json.dumps(data, ensure_ascii=False),
        )
```

### 4. IdTable 재구성

이것이 마이그레이션에서 가장 중요한 단계다.
Full Generation은 IdTable을 사전에 구성하고 LLM에 주입하는데,
가져온 프로젝트는 이미 ID가 정해져 있으므로 역방향으로 재구성한다.

```python
def rebuild_id_table(files: dict[str, Any]) -> IdTable:
    """
    기존 JSON에서 이름→ID 역매핑 추출.
    RPG Maker MZ 규칙: index 0 = null, index i = ID i
    """
    def extract_mapping(data: list) -> dict[str, int]:
        result = {}
        for item in data:
            if item is None:
                continue
            name = item.get("name", "")
            item_id = item.get("id", 0)
            if name and item_id:
                # 이름 중복 시 첫 번째 ID 유지
                if name not in result:
                    result[name] = item_id
        return result

    maps_mapping = {}
    for key, data in files.items():
        if re.match(r"Map(\d{3})\.json$", key):
            map_id = int(re.search(r"\d{3}", key).group())
            map_name = data.get("displayName", key.replace(".json", ""))
            if map_name:
                maps_mapping[map_name] = map_id

    return IdTable(
        actors=extract_mapping(files.get("Actors.json", [])),
        classes=extract_mapping(files.get("Classes.json", [])),
        skills=extract_mapping(files.get("Skills.json", [])),
        items=extract_mapping(files.get("Items.json", [])),
        weapons=extract_mapping(files.get("Weapons.json", [])),
        armors=extract_mapping(files.get("Armors.json", [])),
        enemies=extract_mapping(files.get("Enemies.json", [])),
        troops=extract_mapping(files.get("Troops.json", [])),
        maps=maps_mapping,
    )
```

> **주의**: 가져온 프로젝트는 이름이 비어있는 항목이 있을 수 있다.
> `extract_mapping`에서 name이 빈 문자열인 경우 건너뛴다.
> IdTable에 없는 ID는 Incremental Edit에서 LLM이 숫자로 직접 참조해야 한다.

### 5. generations 레코드 생성

```python
@dataclass
class ImportRecord:
    game_id: str
    source: Literal["user_upload", "template", "api"]
    id_table: IdTable
    summary: ProjectSummary

async def create_import_record(record: ImportRecord, db) -> str:
    """
    Full Generation을 거치지 않은 가져오기용 generations 레코드 생성.
    status='imported'로 구분 (completed와 다름).
    """
    gen_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO generations
            (id, game_id, status, phase, progress,
             source, id_table_snapshot)
        VALUES
            ($1, $2, 'imported', 'import', 100,
             $3, $4)
        """,
        gen_id,
        record.game_id,
        record.source,
        json.dumps(record.id_table.model_dump()),
    )
    await db.execute(
        "UPDATE games SET last_generation_id=$1 WHERE id=$2",
        gen_id, record.game_id,
    )
    return gen_id
```

> **DB 스키마 변경 필요**: `generations` 테이블에 다음 컬럼 추가:
> - `source TEXT` — 'full_gen' | 'user_upload' | 'template' | 'api'
> - `id_table_snapshot JSONB` — 마이그레이션 시점의 IdTable 스냅샷

---

## 가져온 프로젝트의 제약

### Incremental Edit

가져온 프로젝트는 즉시 Incremental Edit 사용 가능하다.
단, 다음 제약이 있다:

| 요청 | 동작 |
|------|------|
| "슬라임 HP 올려줘" | 정상 동작 (ID 조회 없이 이름 기반 검색) |
| "새 스킬 추가해줘" | 정상 동작 (기존 ID 최댓값 + 1 부여) |
| "이벤트 기획자가 쓴 NPC 대화 바꿔줘" | 동작하지 않을 수 있음 (DSL 없음) |

**이름 없는 항목 처리**: Incremental Edit LLM은 `id_table_snapshot`을
참고하되, 없는 이름은 JSON에서 직접 검색한다 (`find_by_name()` 폴백).

### Full Generation 부분 재생성

`id_table_snapshot`이 있으면 부분 재생성 시 이를 초기 IdTable로 사용한다.
단, 부분 재생성이 기존 ID를 덮어쓸 수 있으므로 항상 경고를 표시한다:

```
⚠️ 에셋 재생성 시 기존 ID가 변경될 수 있습니다.
   이벤트가 기존 ID를 참조하고 있다면 이벤트도 함께 재생성하세요.
```

---

## 마이그레이션 후 IdTable 불일치 감지

가져온 프로젝트에서 Incremental Edit 실행 후 IdTable과 실제 JSON이
어긋날 수 있다. 이를 감지하는 검증기:

```python
def check_id_table_consistency(
    id_table: IdTable,
    files: dict[str, Any],
) -> list[str]:
    """
    id_table의 이름→ID와 실제 JSON의 ID가 일치하는지 확인.
    불일치 항목 목록 반환.
    """
    mismatches: list[str] = []

    for actor_name, actor_id in id_table.actors.items():
        actors = files.get("Actors.json", [])
        if actor_id < len(actors) and actors[actor_id]:
            actual_name = actors[actor_id].get("name", "")
            if actual_name != actor_name:
                mismatches.append(
                    f"Actors: id_table['{actor_name}']={actor_id} "
                    f"but JSON[{actor_id}].name='{actual_name}'"
                )
        else:
            mismatches.append(f"Actors: id_table['{actor_name}']={actor_id} not in JSON")

    # 동일하게 skills, items, enemies, maps 검증
    ...
    return mismatches
```

이 검증은 마이그레이션 완료 후와 Incremental Edit 사이클마다 실행한다.

---

## 테스트 픽스처로 사용하기

개발/테스트 환경에서 고정된 RPG Maker MZ 샘플 프로젝트를 로드:

```python
# conftest.py (agent/tests/)

@pytest.fixture
def sample_project() -> dict[str, Any]:
    """agent/tests/fixtures/sample_medieval/ 디렉터리에서 로드."""
    base = Path(__file__).parent / "fixtures" / "sample_medieval"
    files = {}
    for path in base.glob("*.json"):
        files[path.name] = json.loads(path.read_text(encoding="utf-8"))
    return files

@pytest.fixture
def sample_id_table(sample_project) -> IdTable:
    return rebuild_id_table(sample_project)
```

**픽스처 디렉터리 구조**:
```
agent/tests/fixtures/sample_medieval/
├── Actors.json      # 캐릭터 2명 (해럴드, 세라)
├── Classes.json     # 클래스 2개 (전사, 마법사)
├── Skills.json      # 스킬 10개
├── Items.json       # 아이템 8개
├── Weapons.json     # 무기 5개
├── Armors.json      # 방어구 5개
├── Enemies.json     # 적 4종 (슬라임, 고블린, 오크, 드래곤)
├── Troops.json      # 전투 편성 3개
├── System.json
├── Map001.json      # 출발 마을 (30×30)
├── Map002.json      # 숲 (40×30)
└── Map003.json      # 보스 던전 (20×20)
```

이 픽스처는 실제 RPG Maker MZ에서 열 수 있는 최소 유효 프로젝트여야 한다.

---

## 마이그레이션 리스크

### R-M1: 이름 충돌
**상황**: 가져온 프로젝트에 같은 이름의 스킬이 두 개 있음.
**대응**: `extract_mapping`에서 첫 번째 ID만 유지. 경고 표시.

### R-M2: 빈 이름 항목
**상황**: RPG Maker MZ에서 이름을 비워둔 항목 (id=5, name="").
**대응**: IdTable에 포함하지 않음. Incremental Edit에서 숫자 ID로 직접 접근.

### R-M3: ID 불연속
**상황**: id=1, 2, 5 (3, 4 없음) — 사용자가 중간 항목을 삭제한 경우.
**대응**: 그대로 수용. Full Gen과 달리 마이그레이션은 ID 연속성을 강제하지 않음.

### R-M4: 맵 displayName 없음
**상황**: `Map001.json`에 `displayName`이 비어있음.
**대응**: 파일명에서 추출 (`"Map001.json"` → `"Map001"`). 경고 표시.

### R-M5: 50MB 초과 프로젝트
**상황**: 대형 프로젝트 (많은 맵, 커스텀 이미지 등).
**대응**: JSON만 처리 (이미지 제외). 압축 후 50MB 초과 시 거부.

---

## 구현 순서 (integration_with_existing.md 참고)

마이그레이션 기능은 **Sprint 4** (DB + API) 이후에 추가한다:

1. **Sprint 4 완료 후**: `game_files` 테이블, `generations` 테이블 존재
2. **Sprint 6 이후**: `validate_upload` + `store_game_files` 구현
3. **Sprint 8 이후**: `rebuild_id_table` + `create_import_record` 구현
4. **Sprint 9**: 마이그레이션 API 엔드포인트 + 테스트

```python
# 마이그레이션 API 테스트 (Sprint 9)

@pytest.mark.asyncio
async def test_import_valid_project(client, sample_zip):
    response = await client.post(
        "/api/v1/games/test-game/import",
        files={"file": sample_zip},
        data={"overwrite": "false"},
    )
    assert response.status_code == 202

@pytest.mark.asyncio
async def test_import_rebuilds_id_table(client, db, sample_zip):
    await client.post("/api/v1/games/test-game/import", files={"file": sample_zip})
    gen = await db.fetch_one(
        "SELECT id_table_snapshot FROM generations WHERE game_id=$1", "test-game"
    )
    id_table = IdTable.model_validate_json(gen["id_table_snapshot"])
    assert "해럴드" in id_table.actors  # sample_medieval fixture 기준
    assert id_table.actors["해럴드"] == 1

@pytest.mark.asyncio
async def test_import_missing_actors_file_fails(client, incomplete_zip):
    response = await client.post(
        "/api/v1/games/test-game/import",
        files={"file": incomplete_zip},
    )
    assert response.status_code == 422
    assert "Actors.json" in response.json()["detail"]
```
