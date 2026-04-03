# Re:Verse Docs Index

Re:Verse의 문서를 현재 구조 기준으로 정리한 인덱스다.

## 현재 프로젝트 구성

- `app/backend`: FastAPI 백엔드
- `app/frontend`: React/Vite 프런트엔드
- `agent`: LangGraph 기반 에이전트 파이프라인
- `storage/games`: RPG Maker 프로젝트 데이터

핵심 흐름:

1. 사용자가 편집 요청을 입력한다.
2. 프런트엔드가 백엔드 API로 요청을 보낸다.
3. 백엔드가 에이전트 그래프를 호출한다.
4. 에이전트가 RPG Maker JSON을 수정하고 검증한다.
5. 결과를 프런트엔드 뷰어에서 확인한다.


## 문서 구조

```text
docs/
|- index.md
|- backend/
|  |- api.md
|  `- backend_api_spec.md
|- deployment/
|  |- aws_env_setup.md
|  `- deployment.md
|- nodes/
|  |- definition/
|  |  `- plan.md
|  |- executor/
|  |  `- mvp.md
|  |- router/
|  |  `- risks.md
|  `- validator/
|     |- log_plan.md
|     |- merge_notes.md
|     |- output_contract_update.md
|     `- test_run.md
|- project/
|  |- mvp_migration_plan.md
|  |- progress.md
|  `- setup.md
`- rpgmaker/
   |- rpgmaker_structure.md
   `- rpgmaker_tile_rendering.md
```


## 빠른 링크

### 프로젝트

- [프로젝트 개요와 현재 구조](./index.md)
- [로컬 실행 빠른 시작](./project/setup.md)
- [진행 현황과 참고 메모](./project/progress.md)
- [MVP 이식 계획](./project/mvp_migration_plan.md)

### 백엔드

- [백엔드 API 개요](./backend/api.md)
- [백엔드 API 상세 명세](./backend/backend_api_spec.md)

### 배포

- [배포 관련 메모](./deployment/deployment.md)
- [AWS/Vercel 환경 설정](./deployment/aws_env_setup.md)

### 노드별 문서

- [Definition 계획](./nodes/definition/plan.md)
- [Executor MVP 문서](./nodes/executor/mvp.md)
- [Router 리스크 메모](./nodes/router/risks.md)
- [Validator 테스트 실행 가이드](./nodes/validator/test_run.md)
- [Validator 출력 계약 변경](./nodes/validator/output_contract_update.md)
- [Validator 병합 메모](./nodes/validator/merge_notes.md)
- [Validator Loguru 로그 계획](./nodes/validator/log_plan.md)

### RPG Maker

- [RPG Maker 구조 메모](./rpgmaker/rpgmaker_structure.md)
- [RPG Maker 타일 렌더링 메모](./rpgmaker/rpgmaker_tile_rendering.md)


## 현재 validator 상태

현재 `agent/graph/nodes/validator.py` 기준:

- 출력은 Pydantic 모델 기반으로 조합된다.
- 표준 출력 필드는 `validation_results`, `validation_summary`, `success`, optional `retry_count`다.
- 구형 `validation_result`, item-level `message`, `error_count`는 표준 출력에서 제거됐다.
- `model_validate(..., strict=True)`를 사용하므로 문자열 숫자 같은 coercion은 통과하지 않는다.
- CLI 실행은 `agent/tests/test_validator.py`를 사용하며, 현재 import 경로상 `JWT_SECRET_KEY`가 필요하다.


## 문서 관리 규칙

- 문서는 모두 `docs/` 아래에 둔다.
- 파일명은 소문자로 유지한다.
- 노드 관련 문서는 `docs/nodes/{node_name}/` 아래에 둔다.
- 과거 계획 문서는 삭제 대신 현재 상태를 표시하는 메모를 덧붙여 보존한다.
