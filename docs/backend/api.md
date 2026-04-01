# Backend API Overview

현재 백엔드 문서의 진입점이다.

## 현재 상태

- FastAPI 앱 엔트리포인트: `app/backend/main.py`
- API prefix: `/api/v1`
- 현재 주 엔드포인트: `POST /api/v1/llm/process`
- 정적 게임 파일 마운트: `/game`
- 헬스체크: `/health`, `/health/db`, `/health/s3`

## 상세 문서

- 상세 명세: [backend_api_spec.md](./backend_api_spec.md)

## 참고

백엔드 실행과 환경 설정은 [../project/setup.md](../project/setup.md)와 [../deployment/aws_env_setup.md](../deployment/aws_env_setup.md)를 참고한다.
