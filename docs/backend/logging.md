# 로깅 설정 가이드

## 개요

프로젝트 전체(backend + agent)의 로깅을 `shared/logging_config.py`에서 중앙 집중 관리한다.
`app/backend/main.py`의 lifespan 시작 시 `setup_logging()`을 한 번 호출하면, 모든 모듈의 로거에 설정이 적용된다.

## 구조

```
shared/logging_config.py    ← 로깅 설정 모듈 (dictConfig + 커스텀 핸들러)
shared/log_context.py       ← 요청별 유저 컨텍스트 (contextvars)
app/backend/main.py         ← setup_logging() 호출 지점
app/backend/core/security.py ← 인증 시 유저 컨텍스트 설정
```

## 로그 폴더 구조

```
logs/
├── general/                                    # 일반 로그 (모든 레벨, 72시간 보존)
│   └── {YYYY-MM-DD}/
│       └── {username}_{user_id}/
│           └── general.log
└── error/                                      # ERROR/WARNING 전용 (영구 보존)
    └── {YYYY-MM-DD}/
        └── {username}_{user_id}/
            └── {YYYY-MM-DD_HH-MM-SS-mmm}_{LEVEL}.log
```

### 예시

```
logs/
├── general/
│   └── 2026-04-02/
│       ├── anonymous/general.log       # 인증 전 로그
│       ├── genie_1/general.log         # genie (id=1)
│       └── genie_2/general.log         # genie (id=2) — 동명이인 분리
└── error/
    └── 2026-04-02/
        └── genie_1/
            ├── 2026-04-02_14-30-25-038_ERROR.log
            └── 2026-04-02_15-10-42-512_WARNING.log
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
2. 그 외 → **INFO**

## 핸들러

### 콘솔 (stderr)

| 환경 | 포맷 |
|------|------|
| 개발 | `2026-04-02 01:02:21.038 \| INFO     \| nickname_user_id \| agent.editor.nodes.planner \| 메시지` |
| 프로덕션 | `{"timestamp":"...","level":"INFO","user":"nickname_user_id","logger":"...","message":"..."}` |

### 일반 로그 (DailyUserFileHandler)

- 경로: `{LOG_DIR}/general/{YYYY-MM-DD}/{username}_{user_id}/general.log`
- 날짜/유저별 폴더 자동 생성
- **72시간 보존** — 500회 emit마다 오래된 날짜 폴더 자동 삭제
- 포맷: 개발 시 readable, 프로덕션 시 JSON

### 에러/워닝 로그 (ErrorContextHandler)

- 경로: `{LOG_DIR}/error/{YYYY-MM-DD}/{username}_{user_id}/{YYYY-MM-DD_HH-MM-SS-mmm}_{LEVEL}.log`
- WARNING 또는 ERROR 발생 시 **전후 3분(±3분) 컨텍스트**를 포함한 로그 파일 생성
- **영구 보존** — 자동 삭제 없음
- 백그라운드 타이머가 30초 주기로 완료된 캡처를 플러시
- 서버 종료 시 미완료 캡처도 자동 플러시

#### 에러 로그 생성 흐름

```
1. 에러 발생 (20:10:21) → 캡처 시작, 과거 3분(20:07:21~) 로그를 버퍼에서 추출
2. 20:10:21 ~ 20:13:21  → 이후 3분간 발생하는 로그도 계속 수집
3. 20:13:21 이후         → 백그라운드 타이머(30초 주기)가 파일 작성
```

## 유저 컨텍스트

`shared/log_context.py`의 `contextvars`를 통해 요청별 유저 정보를 로그에 자동 주입한다.

### 동작 원리

1. 사용자가 API 요청 (JWT 토큰 포함)
2. `get_current_user()` (security.py)에서 인증 후 `set_current_user(username, user_id)` 호출
3. 이후 해당 요청 내 모든 로그에 `user_label` (예: `genie_1`) 자동 포함
4. 로그 핸들러가 `user_label`을 기반으로 폴더 경로 결정

### 인증 전 로그

인증 전 또는 인증 불필요 엔드포인트의 로그는 `anonymous` 폴더에 저장된다.

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

### 유저 컨텍스트 수동 설정 (테스트용)

agent 단독 테스트에서 유저 컨텍스트를 설정하려면:

```python
from shared.log_context import set_current_user

set_current_user("test_user", 99)
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
- `logs/` 폴더를 삭제해도 다음 로그 발생 시 자동으로 재생성된다.
- SQLAlchemy의 `echo` 옵션은 `False`로 설정되어 있으며, SQL 로그는 `LOG_LEVEL_SQLALCHEMY` 환경변수로 제어한다.
- 프로덕션 Docker 배포 시 `logs/` 볼륨 마운트를 설정하지 않으면 컨테이너 재시작 시 로그가 유실된다.
- 에러 로그는 영구 보존되므로 디스크 사용량을 주기적으로 모니터링할 것을 권장한다.
