# 로깅 설정 가이드

## 개요

프로젝트 전체(backend + agent)의 로깅을 `shared/logging_config.py`에서 중앙 집중 관리한다.
`app/backend/main.py`의 lifespan 시작 시 `setup_logging()`을 한 번 호출하면, 모든 모듈의 로거에 설정이 적용된다.

## 구조

```
shared/logging_config.py    ← 로깅 설정 모듈 (dictConfig 기반)
app/backend/main.py         ← setup_logging() 호출 지점
logs/reverse.log            ← 로그 파일 출력 (자동 생성)
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOG_LEVEL` | 자동 결정 | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LOG_DIR` | `./logs` | 로그 파일 저장 경로 |
| `LOG_LEVEL_SQLALCHEMY` | `WARNING` | SQLAlchemy 로거 레벨 오버라이드 |
| `LOG_LEVEL_HTTPX` | `WARNING` | HTTPX 로거 레벨 오버라이드 |

### LOG_LEVEL 자동 결정 규칙

`LOG_LEVEL`을 설정하지 않으면 아래 순서로 결정된다:

1. `DEBUG=true` → **DEBUG**
2. `ENVIRONMENT=production` → **INFO**
3. 그 외 → **INFO**

## 핸들러

### 콘솔 (stderr)

| 환경 | 포맷 |
|------|------|
| 개발 | `2026-04-02 01:02:21.038 \| INFO     \| agent.graph.nodes.planner \| 메시지` |
| 프로덕션 | `{"timestamp":"2026-04-02T01:02:21.038+00:00","level":"INFO","logger":"...","message":"..."}` |

### 파일 (RotatingFileHandler)

- 경로: `{LOG_DIR}/reverse.log`
- 최대 크기: 10MB
- 백업 파일 수: 5개 (최대 ~60MB)
- 인코딩: UTF-8
- 포맷: 개발 시 readable, 프로덕션 시 JSON

## 로거별 레벨 제어

| 로거 | 레벨 | 비고 |
|------|------|------|
| `agent.*` | LOG_LEVEL | agent 파이프라인 전체 |
| `app.backend.*` | LOG_LEVEL | backend 서비스 전체 |
| `shared.*` | LOG_LEVEL | 공용 모듈 |
| `sqlalchemy` | LOG_LEVEL_SQLALCHEMY (기본 WARNING) | DB 쿼리 로그 |
| `httpx` | LOG_LEVEL_HTTPX (기본 WARNING) | HTTP 클라이언트 로그 |
| `uvicorn` | INFO (고정) | 서버 이벤트 |
| root | WARNING (고정) | 미등록 로거 안전망 |

## 사용 방법

### 각 모듈에서 로거 사용 (기존 패턴 유지)

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("상세 디버깅 정보: %s", data)
logger.info("[NodeName] 노드 진입")
logger.warning("예상치 못한 상태: %s", state)
logger.error("처리 실패: %s", error, exc_info=True)
```

### agent 단독 테스트 시

backend를 실행하지 않고 agent만 테스트할 경우, 테스트 파일 상단에서 직접 호출한다:

```python
from shared.logging_config import setup_logging

setup_logging()
```

## .env 설정 예시

```ini
# 개발 환경 (DEBUG 로그 전부 출력)
LOG_LEVEL=DEBUG
LOG_DIR=./logs

# 프로덕션 환경 (INFO 이상만 출력, JSON 포맷)
LOG_LEVEL=INFO
LOG_DIR=./logs
ENVIRONMENT=production

# SQLAlchemy 쿼리 디버깅이 필요할 때
LOG_LEVEL_SQLALCHEMY=DEBUG
```

## 참고

- `logs/` 디렉토리는 `.gitignore`에 등록되어 있어 커밋되지 않는다.
- SQLAlchemy의 `echo` 옵션은 `False`로 설정되어 있으며, SQL 로그는 `LOG_LEVEL_SQLALCHEMY` 환경변수로 제어한다.
- 프로덕션 Docker 배포 시 `logs/` 볼륨 마운트를 설정하지 않으면 컨테이너 재시작 시 로그가 유실된다.
