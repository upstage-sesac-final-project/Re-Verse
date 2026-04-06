# Phase 7 — DB 영속성

> 상태: 미구현
> 우선순위: **높음** — 현재 서버 재시작 시 모든 생성 이력 손실

---

## 문제

현재 `_generation_states: dict[str, GenerationStatusResponse]`는 in-memory.
FastAPI 프로세스 재시작 시 모든 상태 날아감. 사용자가 나중에 결과를 다시 못 봄.

---

## 구현 대상

### DB 스키마 (`generations` 테이블)

```sql
CREATE TABLE generations (
    id           TEXT PRIMARY KEY,          -- gen_xxxxxxxx
    user_id      INTEGER REFERENCES users(id),
    project_id   INTEGER REFERENCES projects(id),
    status       TEXT NOT NULL DEFAULT 'started',
    progress     INTEGER DEFAULT 0,
    prompt       TEXT,
    phase_limit  TEXT,
    completed_phases  TEXT[],
    final_project     JSONB,               -- 전체 생성 파일 (크기 주의)
    validation_errors TEXT[],
    validation_warnings TEXT[],
    final_message TEXT,
    is_success   BOOLEAN,
    error_message TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);
```

> **주의**: `final_project`는 JSONB. Map 타일 배열 포함 시 약 2~5MB.
> 필요하면 `map_tiles`만 별도 컬럼으로 분리하거나 S3에 저장 고려.

### 백엔드 변경

**`app/backend/db/`** — `generation_repo.py` 추가
```python
async def upsert_generation(gen: GenerationRecord) -> None: ...
async def get_generation(gen_id: str, user_id: int) -> GenerationRecord | None: ...
async def list_generations(user_id: int, project_id: int) -> list[GenerationRecord]: ...
```

**`generation.py`** 엔드포인트 변경:
- `_generation_states` dict 제거
- 모든 읽기/쓰기를 `generation_repo`로 교체
- 백그라운드 태스크에서 단계별 `upsert_generation` 호출

### 프론트엔드 변경

**`Dashboard.jsx`** — 프로젝트별 최근 생성 이력 표시
**`GeneratePage.jsx`** — 이전 생성 결과 복원 (generationId가 URL에 있으면 조회)

---

## 완료 기준

- [ ] 서버 재시작 후 `GET /api/v1/generate/{id}/status` 200 반환
- [ ] 프로젝트 페이지에서 최근 생성 이력 목록 표시
- [ ] `final_project` DB 저장 + 다운로드 엔드포인트 연동
