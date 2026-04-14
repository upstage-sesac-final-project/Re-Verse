# 동시성 문제 감사 및 개선 계획

> 작성일: 2026-04-14
> 대상: 다수 사용자 동시 접속 시 발생 가능한 문제

## Phase 1: DB 커넥션 풀 + 인메모리 상태 정리 (즉시)

가장 시급한 문제. 현재 발생 중인 에러 포함.

### 1-1. DB 커넥션 풀 고갈
- **파일**: `app/backend/db/session.py`
- **현상**: `QueuePool limit of size 5 overflow 10 reached, connection timed out`
- **원인**: 기본 pool_size=5, max_overflow=10. 생성 워크플로우가 커넥션을 장시간 점유.
- **수정**: pool_size 확대 + pool_recycle 설정 + pool_pre_ping 활성화

### 1-2. 인메모리 생성 상태 메모리 누수
- **파일**: `app/backend/api/v1/endpoints/generation.py:42-48`
- **현상**: `_generation_states`, `_generation_owners`, `_project_generations` dict가 무한 증가
- **수정**: 완료 후 일정 시간 뒤 자동 정리 (TTL)

### 1-3. 이벤트 큐 정리 안 됨
- **파일**: `agent/generation/progress.py`
- **현상**: `_pending_events` dict 만료 없음. WS 끊기면 큐 고아화.
- **수정**: subscribe 종료 시 cleanup 보장

---

## Phase 2: 파일 시스템 동시 접근 보호 (단기)

### 2-1. 생성 중 파일 쓰기 충돌
- **파일**: `agent/generation/writer.py`
- **현상**: 생성이 파일을 쓰는 도중 에디터가 같은 파일 읽으면 깨진 JSON
- **수정**: 파일 쓰기 시 임시 파일 → atomic rename 패턴

### 2-2. S3 업로드 중 파일 변경
- **파일**: `app/backend/services/s3_game_storage.py`
- **현상**: 에디터 퇴장 → S3 업로드 도중 생성이 로컬 파일 수정
- **수정**: 업로드 전 스냅샷 생성 또는 순서 보장

---

## Phase 3: 비즈니스 로직 보호 (중기)

### 3-1. 프로젝트 3개 제한 우회
- **파일**: `app/backend/services/game_service.py:29-40`
- **현상**: 동시 요청 시 count 체크를 다 통과해서 제한 초과
- **수정**: DB 레벨 제약조건 또는 비관적 Lock

### 3-2. 에디터 세션 경쟁 조건
- **파일**: `app/backend/services/session_manager.py:33-39`
- **현상**: is_active() → register_session() 사이에 다른 유저 진입 가능
- **수정**: asyncio.Lock으로 원자적 체크+등록

### 3-3. 게임 Lock 생성 경쟁
- **파일**: `app/backend/services/session_manager.py:71-72`
- **현상**: 동시에 Lock 객체 2개 생성 → 상호 배제 실패
- **수정**: defaultdict(asyncio.Lock) 또는 별도 Lock으로 보호

---

## Phase 4: API 안정성 (중기)

### 4-1. LLM 세마포어 멀티 워커 무력화
- **파일**: `agent/core/llm_client.py:20`
- **현상**: 멀티 프로세스 시 프로세스당 세마포어 → 실제 제한 없음
- **수정**: 단일 프로세스 운영 확인 또는 Redis 기반 분산 세마포어

### 4-2. WS 커넥션 누수
- **파일**: `app/backend/api/v1/endpoints/generation.py`
- **현상**: WS disconnect 시 큐 정리 누락 가능
- **수정**: finally 블록에서 큐 명시적 정리
