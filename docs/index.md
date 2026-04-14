# Re:Verse Docs Index

## 프로젝트 구성

- `app/backend` — FastAPI 백엔드
- `app/frontend` — React/Vite 프런트엔드
- `agent` — LangGraph 기반 에이전트 (Editor / Generator 두 파이프라인)
- `storage/games` — RPG Maker 프로젝트 데이터

핵심 흐름: 사용자 입력 → 프런트 → 백엔드 API → 에이전트 그래프 → RPG Maker JSON 수정·검증 → 프런트 뷰어.

## 문서 구조

```text
docs/
├── index.md
├── editor.md                — 증분 편집 에이전트 워크플로우 (router/reader/definition/planner/executor/validator)
├── generator.md             — 전체 게임 생성 파이프라인 (A~J 노드)
├── todo/
│   ├── map_crud.md          — Reader/Definition/Planner 맵 지원 계획
│   └── todolist-editor.md
├── backend/
│   ├── api.md               — 전체 API 명세
│   ├── storage.md           — 게임 파일 저장/최적화
│   └── logging.md
├── deployment/
│   └── deployment.md        — AWS/Vercel 환경 설정 + 배포
└── rpgmaker/
    ├── structure.md
    ├── tile_rendering.md
    └── image_metadata.md
```

## 빠른 링크

- **에이전트 워크플로우**: [editor.md](./editor.md) · [generator.md](./generator.md)
- **할 일**: [todo/todolist-editor.md](./todo/todolist-editor.md) · [todo/map_crud.md](./todo/map_crud.md)
- **백엔드**: [backend/api.md](./backend/api.md) · [backend/storage.md](./backend/storage.md) · [backend/logging.md](./backend/logging.md)
- **배포**: [deployment/deployment.md](./deployment/deployment.md)
- **RPG Maker 참고**: [rpgmaker/structure.md](./rpgmaker/structure.md) · [rpgmaker/tile_rendering.md](./rpgmaker/tile_rendering.md) · [rpgmaker/image_metadata.md](./rpgmaker/image_metadata.md)

## 문서 관리 규칙

- 모든 문서는 `docs/` 아래에 둔다. 루트에는 `CLAUDE.md`, `README.md`만.
- 파일명은 `snake_case.md`.
- 에이전트 파이프라인 문서는 노드별로 쪼개지 않고 `editor.md` / `generator.md` 한 장씩으로 유지한다.
- 작업 계획·할 일은 `todo/`에 둔다.
