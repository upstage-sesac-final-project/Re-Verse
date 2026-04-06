# Phase 6 — 게임 파일 다운로드

> 상태: 미구현
> 우선순위: **긴급** — 없으면 생성된 게임을 실제로 쓸 수 없음

---

## 목표

`final_project` dict(메모리) → RPG Maker MZ 프로젝트 ZIP → 사용자 다운로드

---

## 구현 대상

### 백엔드

**`app/backend/api/v1/endpoints/generation.py`** — 다운로드 엔드포인트 추가

```python
@router.get("/{generation_id}/download")
async def download_generation(generation_id: str, current_user: User = Depends(...)):
    """생성된 RPG Maker MZ 프로젝트를 ZIP으로 반환."""
    state = _generation_states.get(generation_id)
    if not state or state.status not in ("completed", "completed_with_warnings"):
        raise HTTPException(404)

    final_project = state.final_project  # dict[str, Any]
    zip_bytes = _build_zip(final_project)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=game_{generation_id}.zip"},
    )
```

**`_build_zip(final_project)` 구현:**
```
www/data/
├── Actors.json
├── Classes.json
├── ...
├── System.json
├── MapInfos.json
├── Map001.json
├── Map002.json
└── ...
```

- `GenerationStatusResponse`에 `final_project` 필드 추가 (or 별도 저장소)
- `_run_generation_in_background`에서 `final_project` 저장 처리

### 프론트엔드

**`GenerationResult.jsx`** — 다운로드 버튼 추가

```jsx
<button onClick={() => downloadProject(generationId)}>
  RPG Maker 프로젝트 다운로드 (.zip)
</button>
```

**`generationApi.js`** — `downloadGeneration(generationId)` 함수
- `authFetch`로 binary response 처리
- `URL.createObjectURL` + `<a>` 클릭 트릭

---

## 완료 기준

- [ ] `GET /api/v1/generate/{id}/download` 200 반환, ZIP 파일 유효
- [ ] ZIP 압축 해제 시 `www/data/*.json` 구조 확인
- [ ] RPG Maker MZ에서 직접 열기 가능 (수동 검증)
- [ ] 프론트엔드 다운로드 버튼 클릭 → 파일 저장 다이얼로그

---

## 주의사항

- `final_project`가 현재 `GenerationStatusResponse`에 없음 → 저장 구조 변경 필요
- `Map*.json`의 `data` 배열이 크므로 ZIP 압축률이 높음 (zlib deflate)
- 인증된 사용자만 자신의 generation 다운로드 가능 (소유권 체크)
