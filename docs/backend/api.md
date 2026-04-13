# Backend API Overview

백엔드 문서의 진입점입니다.

## 현재 상태

- FastAPI 앱 엔트리포인트: `app/backend/main.py`
- API prefix: `/api/v1`
- 헬스체크: `/health`, `/health/db`, `/health/s3`
- 게임 정적 파일: `/game/{game_id}/` (인증 불필요)

## API 목록

| 엔드포인트 그룹 | prefix | 설명 |
|---------------|--------|------|
| Auth | `/api/v1/auth` | 회원가입, 로그인, 토큰 갱신/폐기 |
| Games | `/api/v1/games` | 프로젝트 CRUD |
| LLM | `/api/v1/llm` | 채팅 기반 증분 편집 |
| Editor | `/api/v1/editor` | S3 ↔ 로컬 세션 동기화 |
| Generation | `/api/v1/generate` | 프롬프트 기반 게임 풀 생성 (비동기 + WebSocket) |

## 상세 문서

- **API 전체 명세**: [backend_api_spec.md](./backend_api_spec.md)
  - 인증 보안 패턴 (JWT, 소유권 확인, WebSocket 인증)
  - 각 엔드포인트 Request/Response 스키마
  - 에러 응답 형식
  - 환경 변수 목록

- **게임 파일 저장 흐름**: [game_storage_flow.md](./game_storage_flow.md)
- **로깅**: [logging.md](./logging.md)

## 참고

백엔드 실행 및 환경 설정은 [../project/setup.md](../project/setup.md)와
[../deployment/aws_env_setup.md](../deployment/aws_env_setup.md)를 참고하세요.
