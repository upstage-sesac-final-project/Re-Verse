# TODO List - Deploy

## [기록] 이번 배포 수정 방향 (2026-04-14)

### 문제
- develop → main PR 후 배포 단계에서 `docker build` 실패
- 실패 지점: `docker/backend.Dockerfile:17` mcp-builder 스테이지의 RUN 블록
  ```
  process "/bin/sh -c set -eux; git clone ... npm ci ... npm run build ..." exit code: 1
  ```

### 원인 분석
1. **소스 불일치**: Dockerfile이 upstream `rein1225/RPGMakerMZ_MCP.git`을 매 빌드마다 git clone 중. 하지만 실제로는 레포 내부 `mcp/integration_MCP/`가 통합본으로 들어와 있어서 upstream을 쓸 이유가 없어진 상태. Dockerfile만 옛 경로 유지.
2. **alpine 환경 + upstream 의존성 조합 문제**:
   - upstream `package.json`의 devDependency `robotjs` — 네이티브 모듈. `node-gyp` 컴파일 필요하지만 alpine에 python3/make/g++/X11 헤더 없음 → 설치 단계에서 실패
   - dependency `puppeteer` — postinstall이 Chromium ~170MB 다운로드 → CI 네트워크/용량 이슈로 실패 가능
   - `set -eux`라 둘 중 하나만 삐끗해도 exit 1

### 초기 선택(Option 2) → 실패 → 최종 선택(Path E)

#### Option 2 (로컬 COPY + ignore-scripts) — ❌ CD 실행에서 실패
- `git clone` 제거 → `COPY mcp/integration_MCP` 로 전환 시도
- **실패 원인**: `mcp/integration_MCP/`가 Re-Verse 레포에 커밋되어 있지 않음 (nested git repo 상태, 사용자 로컬 파일시스템에만 존재). CD 러너는 체크아웃한 Re-Verse 레포만 가지고 빌드하므로 `COPY` 대상이 없어 `"/mcp/integration_MCP": not found` 에러 발생.
- 추가 발견: `mcp/integration_MCP`의 `origin`이 Dockerfile이 clone하던 `rein1225/RPGMakerMZ_MCP`와 동일. 즉 "통합본"은 upstream의 포크 + 로컬 미커밋 수정본. 양쪽 원격 어디에도 push 안 된 상태였음.

#### Path E (최종 채택) — MCP 스테이지 통째 제거 + executor_v2 경로로 운영
- Dockerfile에서 `mcp-builder` 스테이지 전체 삭제
- `COPY --from=mcp-builder`, `ln -s /app/mcp/default`, `ENV MCP_NODE_SERVER_PATH`, nodejs 설치 블록 모두 제거
- Dockerfile에 `ENV MCP_ENABLED=false` 베이스라인 추가
- `docker-compose.prod.yml`의 `environment:`에도 `MCP_ENABLED=false` 명시해 env_file 값을 override
- `.dockerignore`의 `mcp/` 전체 차단 라인 복원 (빌드 컨텍스트에 불필요)
- `DEBIAN_FRONTEND=noninteractive`, `uv sync` 2단계 분리 유지

**작동 근거**:
- `agent/editor/nodes/executor.py`는 `MCP_ENABLED=false`이면 자동으로 `executor_v2.dispatch`로 fallback
- `agent/editor/nodes/executor_v2/`에 MCP 의존성 0건 (grep 확인)
- 지원 파일: Actors, Classes, Skills, Items, Weapons, Armors, Enemies, States, System, Map### — RPG Maker 핵심 편집 범위 커버
- pytest `test_mcp_toolbox.py`, `test_mcp_server_resolve.py`는 monkeypatch 기반 순수 단위 테스트 → MCP 바이너리 미호출로 CI 영향 없음

### 대안 검토와 기각 사유
- **Option 1 (`--ignore-scripts`만 추가, git clone 유지)**: CI는 살지만 upstream엔 통합본 수정이 push 안 됨 → 런타임에 MCP 기능 대거 불일치 예상.
- **Option 3 (`dist/` 를 레포에 커밋)**: 런타임 `node_modules` 필요해서 반쪽짜리.
- **Option 4 (alpine에 빌드툴 설치)**: robotjs alpine 빌드 historically 불안정.
- **Path B (로컬 수정을 upstream에 push 후 clone)**: upstream 레포 권한 이슈 + 타 레포 관리 오버헤드 → 이번 배포엔 부적합.
- **Path C (integration_MCP를 Re-Verse에 통째 commit)**: 수천 파일 diff 폭증, 배포 스코프 초과.

### 알려진 한계 (배포 후 후속 조치 필요 시)
- **MCP 전용 고급 기능**: Troops.json, CommonEvents.json, Animations.json, Tilesets.json 등 executor_v2 미지원 파일 호출 시 "지원하지 않는 target_file" 에러. 핵심 편집 플로우 아니면 영향 제한적.
- MCP 기능 복귀하려면 (1) integration_MCP 소스를 레포에 committable 형태로 정리 → (2) Dockerfile mcp-builder 복원 → (3) `MCP_ENABLED=true`. 별도 PR로.
- EC2 루트 디스크 압박(overlay2 2.4GB)은 이번 PR 범위 밖 — 아래 "빌드 캐시 자동 정리" 항목에서 별도 처리. **부수 효과: Path E로 이미지 크기 크게 감소(Node.js + MCP 산출물 제거)** — 디스크 압박 일부 자동 완화.

### 검증 체크리스트
- [x] executor_v2의 MCP 의존성 부재 확인 (`agent/editor/nodes/executor_v2/` grep)
- [x] executor가 `MCP_ENABLED=false`에서 v2로 fallback함 확인 (`agent/mcp_toolbox.py:49`, `executor.py:1719`)
- [x] executor_v2 지원 파일 범위 확인 (`handlers/entity.py:20` ALL_SUPPORTED)
- [x] pytest MCP 관련 테스트가 바이너리 미호출 확인 (monkeypatch only)
- [x] `.github/workflows/deploy.yml`이 단순 SSH + `docker compose up --build` 구조 확인 → 추가 수정 불필요
- [x] `.github/workflows/ci.yml` pytest가 MCP 호출 안 함 확인
- [ ] 로컬 `docker build -f docker/backend.Dockerfile .` 성공 (사용자 환경에서 확인)
- [ ] EC2 `.env.production`에 `MCP_ENABLED=true`가 있는지 확인 후 필요 시 제거/false로 변경 (compose env로 override되지만 명시적 정리 권장)

---

## 빌드 캐시 자동 정리

### 배경
- EC2 루트 볼륨 8GB 중 `/var/lib/docker`가 4.5GB 차지
- 내역: active image ~1.98GB, overlay2 ~2.4GB, build cache ~136MB
- overlay2/이미지 레이어가 매 빌드마다 누적되어 디스크 압박 유발
- 캐시는 Docker 데몬(호스트) 레벨 관리이므로 Dockerfile 안에서 해결 불가 → 빌드 커맨드 바깥에서 청소해야 함

### 옵션 비교 (실행 전 선택 필요)

#### Option A. CI/CD 스크립트에 prune 스텝 추가
- 대상 파일: `.github/workflows/deploy.yml`
- docker build 스텝 직후 한 줄 추가
  ```yaml
  - name: Prune old build cache
    run: docker builder prune -af --filter until=24h
  ```
- 장점: 레포에서 관리됨, PR 리뷰 가능, 배포 파이프라인과 동기화
- 단점: CI가 매번 돌릴 때마다 실행 → 24h 필터 없으면 다음 빌드 캐시 miss
- 추가 파일 필요: ❌

#### Option B. EC2 cron으로 주기 청소
- EC2에서 직접 설정:
  ```
  0 3 * * * /usr/bin/docker system prune -af --volumes >> /var/log/docker-prune.log 2>&1
  ```
- 장점: 빌드 파이프라인과 독립, 설정 한 번이면 끝
- 단점: 레포에 흔적 없음(설정이 서버에만 존재), 팀 인수인계 시 놓치기 쉬움
- 추가 파일 필요: ❌ (서버 crontab)

#### Option C. 배포 스크립트에 prune 추가
- 대상 파일: 배포 셸 스크립트가 있다면 거기에 build 뒤 한 줄
- 현재 레포에 `deploy.sh` 류 없으면 해당 없음
- 추가 파일 필요: ❌

### 결정 시 고려사항
- `--filter until=24h`로 **오래된 캐시만** 지우기 (통째로 날리면 다음 빌드 시간 ↑)
- `docker system prune --volumes`는 볼륨도 지워서 위험 → DB 볼륨 쓰는 서비스면 절대 쓰면 안 됨
- A + B 조합도 가능 (CI에서 24h 필터로 일상 정리, B는 주 1회 deep clean)

### 우선순위
- **배포 안정화 이후** 진행 (현재는 CI/CD 에러 해결이 선결)
- EC2 디스크 다시 80% 넘어가기 전에 결정

### 배포 후 업데이트 (Path E 배포 직후 확인)
- `/var/lib/docker` 5.5GB, 그중 **Build Cache 3.088GB 전부 reclaimable**
- 원인: Dockerfile의 `RUN --mount=type=cache,target=...` (apt/pip/uv) 캐시 마운트가 BuildKit builder cache에 누적
- 기존 `deploy.yml`의 `docker image prune -f`는 dangling 이미지만 청소 → builder cache는 별개
- → Option A 채택 유력. `docker builder prune -af` (필터 없이 전체) 추가 권장
  - 8G 루트 환경에서는 캐시 재사용 이득보다 디스크 안전 우선
  - 다음 빌드 5~10분 느려지지만 허용 가능

---

## 배포 담당자 논의 전 준비 가능한 작은 조치들

integration_MCP 운영 방식은 배포 담당자와 논의가 필요하지만, 그 전에 부담 없이 할 수 있는 것들.

### 1. Builder cache prune 자동화
- 대상: `.github/workflows/deploy.yml`
- `docker compose up -d --build` 이후에 한 줄 추가:
  ```yaml
  docker builder prune -af
  ```
- 근본 해결은 아니지만 재발 방지 안전망
- 영향 범위: 배포 파이프라인에 10~20초 추가, 다음 빌드는 캐시 miss

### 2. EC2 상태 모니터링 습관
- `df -h /` 로 루트 사용량 주기 확인
- `docker system df` 로 이미지/빌드캐시/볼륨 분리 확인
- 6GB 근처 가면 수동 prune 또는 알람
- CloudWatch Alarm 설정 가능하지만 비용·권한 별도 확인

### 3. integration_MCP 로컬 변경분 백업
- 현재 사용자 로컬에만 있는 수정본이 **어느 원격에도 push 안 됨** → 소실 위험
- 배포 담당자 논의 전에 안전 조치:
  - 옵션 a: rein1225 레포에 `wip/integration-local` 같은 브랜치로 push (쓰기 권한 필요)
  - 옵션 b: 별도 fork 레포 만들어서 push
  - 옵션 c: 로컬에서 bundle 파일(`git bundle create`)로 저장
- 어떤 조합(1A/1B/1C × 2A/2B/2C)으로 결정되든 이 수정본은 다시 활용돼야 함

---

## 컴파일 워커 분리 (worker pool 도입 검토)

### 배경
- 현재 컴파일(=full generation)이 API 서버 프로세스 안에서 `BackgroundTasks` + `asyncio.Semaphore(1)`로 돌아감 (`app/backend/api/v1/endpoints/generation.py`)
- 컴파일은 게임 파일 생성 + 다수 LLM 호출 → CPU/메모리 둘 다 무거움
- 인스턴스 스펙: t3.micro(1GB) → **t3.small(2GB)** 로 변경 가능. 그래도 작아서 동시 1~2개가 한계
- 인메모리 상태(`_generation_states`, `_generation_owners`, `_project_generations`, `_generation_queue`)가 전부 프로세스 메모리 → 재배포/재시작 시 진행 중 작업과 큐 통째 유실
- `_generation_semaphore._value` private 접근 + deque 조작 혼재 → race condition 잠재

### 분리의 진짜 이유
"성능"이 아니라 **격리(isolation)** + **재시작 안전성**.
- 컴파일 OOM이 API까지 죽이는 현 구조 해소
- 배포 중에도 큐/진행 상태 보존
- 향후 워커만 별도 스케일 가능

### 세마포어 vs job queue 비교
| 항목 | 현재 (Semaphore) | Queue + Worker |
|---|---|---|
| 동시성 제한 | O | O |
| 재시작 시 큐 보존 | X | O |
| 컴파일 OOM이 API 죽임 | 예 | 아니오 |
| 다중 인스턴스 확장 | X | O |
| 재시도/실패 가시성 | 직접 구현 | 라이브러리 제공 |

### 환경 제약 (교육용 AWS 계정)
- AWS Academy / Educate 류 → 사용 가능 자원 제한
- ✅ 가능: EC2 (t3.micro/small), S3, RDS, EIP 1개, `LabRole` 공유
- ❌ 막힘 가능: ElastiCache, ALB, IAM 사용자/역할 신규 생성, Route53
- 세션 종료 시 EC2 stop → **stale job 처리 필수**

### 채택 후보 스택
- **arq + Redis** (asyncio 네이티브, 코드가 전부 async라 자연스러움)
- Redis는 ElastiCache 못 쓰면 EC2 위에 docker로 직접 (메모리 ~50MB)
- Celery는 t3.small에도 무거움 → 제외

### 1차 설계 (단일 EC2 + 내부 워커 분리)
```
[EIP] → [API EC2 t3.small]
            ├─ FastAPI (uvicorn)
            ├─ arq Worker (max_jobs=1)
            └─ Redis (docker, 큐 + 상태 + pub/sub)
                  ↓
            [S3] [RDS]
```
- 같은 EC2 안에서 컨테이너만 분리 → 격리는 약하지만 코드/배포 구조 검증 목적
- 인메모리 상태 → Redis hash 이전, 세마포어 → arq `max_jobs=1` 이전
- WS 진행률은 Redis pub/sub 경유

### 2차 확장 (멀티 인스턴스, 필요 시)
```
[EIP] → [API EC2 t3.small (Redis 동거)]
              │
              ├─→ [Worker EC2 t3.small #1] (private IP only)
              ├─→ [Worker EC2 t3.small #2]
              └─→ [Worker EC2 t3.small #N]
                       ↓
                  [S3 단일 버킷] (LabRole 공유)
                  [RDS Postgres]
```
- API 인스턴스에만 EIP, 워커는 outbound만이라 private IP로 충분
- 모든 EC2에 동일 `LabRole` 부여 → S3 접근 그대로 동작 (`s3_game_storage.py`가 이미 IAM 역할 기반)
- ALB 없이 운영 (교육 계정 비용/제약 회피)

### 멀티 인스턴스 시 필수 추가 항목
- **game_id 단위 분산 락** (Redis `SET NX EX`)
  - 동일 game_id를 두 워커가 동시 처리 시 S3 last-write-wins로 변경 유실 발생
  - 워커가 작업 시작 전 `lock:game:{game_id}` 획득, 종료 시 해제
- **stale job sweeper**
  - in_progress 상태로 1시간 이상 업데이트 없으면 자동 `failed` 전환
  - 세션 종료/인스턴스 stop 대비 필수
- **EIP release 정책**
  - detach 상태에서 시간당 과금 → 인스턴스 terminate 시 명시적 release

### 작업 순서 (중요: 단계 건너뛰지 말 것)
- [ ] **Step 1**: 코드 리팩터링 — 인메모리 상태(`_generation_states` 등) → Redis hash 이전, 세마포어 → arq `max_jobs=1`. **단일 인스턴스에서 먼저 검증**
- [ ] **Step 2**: docker-compose에 `worker`, `redis` 서비스 추가. 같은 EC2 내부 컨테이너 분리로 동작 확인
- [ ] **Step 3**: 워커 죽여도 API 살아있는지, 워커 재시작 시 큐 보존되는지 검증
- [ ] **Step 4**: 워커 EC2 1대 분리. game_id 단위 Redis 락 도입
- [ ] **Step 5**: stale job sweeper 추가
- [ ] **Step 6**: 필요 시 워커 N대로 확장

### 일부러 1차에서 안 하는 것
- 재시도 정책, dead-letter, 우선순위 큐 → arq 기본값 활용
- ALB + 다중 API 인스턴스 → 교육 계정 비용/제약상 비현실적
- ElastiCache → 차단 가능성 + EC2 docker redis로 충분

### 사전 확인 필요
- [ ] 교육 계정 종류 확정 (Academy Learner Lab? Educate? Sandbox?)
- [ ] 세션 모델 (always-on / N시간 stop)
- [ ] 잔여 크레딧 / 종료 예정일
- [ ] vCPU 서비스 쿼터 (Service Quotas → "Running On-Demand Standard instances")
- [ ] ElastiCache, ALB 사용 가능 여부 (콘솔에서 직접 시도해 확인)
- [ ] EC2 `.env.production`에 Redis URL 추가 가능 여부

### 결정 보류 / 배포 담당자 논의 필요
- 단일 EC2 동거(1차) 후 멀티 인스턴스(2차)로 진행할지, 1차에서 멈출지
- 워커 인스턴스 수와 동시 컴파일 한도 (t3.small 1대당 1개 권장)
- 세션 종료 정책에 맞춘 운영 시간대 제한 도입 여부

---

## 컨테이너 로그를 CloudWatch Logs로 영속화

### 배경
- Docker 기본 로깅 드라이버(`json-file`)는 로그를 `/var/lib/docker/containers/<id>/<id>-json.log`에 저장
- 컨테이너 삭제 시(`docker rm`, `docker system prune` 등) 로그 파일도 함께 소실
- 2026-04-15 빌드 캐시 정리 목적의 `docker system prune -af --volumes` 실행 중 이전 backend 컨테이너가 삭제되며 유저 활동 로그 유실 발생
- 재배포로 올라온 컨테이너는 ID가 달라 로그가 처음부터 다시 쌓이는 중

### 목표
- 컨테이너가 재생성돼도 로그가 유지되도록 외부 저장소로 이관
- CD/prune/재배포 어떤 사이클에서도 로그 연속성 보장

### 채택: awslogs 드라이버 (CloudWatch Logs)
- EC2 이미 AWS 환경이라 별도 인프라 추가 없음
- `LabRole` 또는 동등 IAM 역할이 `logs:CreateLogStream`, `logs:PutLogEvents` 권한 보유 시 즉시 사용 가능
- 교육 계정 제약 내에서 가장 저비용 경로

### 작업 순서
- [ ] **Step 1**: EC2 IAM 역할의 CloudWatch Logs 권한 확인
  - 필요 권한: `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`
  - `LabRole`에 기본 포함 여부 확인. 없으면 로그 그룹 사전 생성으로 회피 가능
- [ ] **Step 2**: CloudWatch Log Group 사전 생성
  - 이름 예시: `/re-verse/backend`, `/re-verse/nginx`
  - 보존 기간 설정 (예: 14일 — 교육 계정 비용 절감)
- [ ] **Step 3**: `docker-compose.prod.yml`의 각 서비스에 `logging` 블록 추가
  ```yaml
  services:
    backend:
      # ... 기존 설정 ...
      logging:
        driver: awslogs
        options:
          awslogs-region: ap-northeast-2
          awslogs-group: /re-verse/backend
          awslogs-stream: backend-${HOSTNAME:-ec2}
          awslogs-create-group: "true"   # Step 2 생략 시
    nginx:
      # ... 기존 설정 ...
      logging:
        driver: awslogs
        options:
          awslogs-region: ap-northeast-2
          awslogs-group: /re-verse/nginx
          awslogs-stream: nginx-${HOSTNAME:-ec2}
  ```
- [ ] **Step 4**: 배포 후 CloudWatch 콘솔에서 스트림 생성 및 로그 수신 확인
- [ ] **Step 5**: 기존 `docker logs` 기반 디버깅 플로우를 CloudWatch 쿼리(Logs Insights)로 전환
- [ ] **Step 6** (선택): 유저 활동 로그를 **stdout 뿐만 아니라 `~/Re-Verse/storage/logs/app.log`에도 병행 기록** — CloudWatch 장애/권한 문제 발생 시 폴백

### 주의사항
- `awslogs` 드라이버는 컨테이너 stdout/stderr만 수집. 앱이 파일 로그만 쓰면 수집 안 됨 → 로거 설정이 stdout으로 내보내는지 확인 필요
- IAM 권한 누락 시 컨테이너 시작 자체가 실패할 수 있음 → 우선 staging 성격으로 한 서비스에만 적용 후 확인
- `awslogs-stream` 이름이 고정이면 동일 인스턴스 재배포 시 같은 스트림에 누적됨. 멀티 인스턴스 확장 시에는 인스턴스 ID 기반 네이밍 필요

### 대안 (채택 보류)
- **앱 레벨 파일 로그 + bind mount** (`~/Re-Verse/storage/logs/`)만 쓰기 — 간단하지만 EC2 날아가면 로그도 소실, 멀티 인스턴스 확장 시 분산됨
- **Loki + Promtail** — 집계/검색 강력하나 t3.small에 부담, 운영 부담 증가
- **Fluent Bit → S3** — awslogs보다 저장 비용 낮지만 실시간 조회 불편

### 사전 확인 필요
- [ ] EC2 인스턴스에 붙은 IAM 역할 이름
- [ ] 해당 역할에 `CloudWatchLogsFullAccess` 또는 동등 권한 유무
- [ ] ap-northeast-2에서 CloudWatch Logs 콘솔 접근 가능 여부 (교육 계정 차단 여부)
