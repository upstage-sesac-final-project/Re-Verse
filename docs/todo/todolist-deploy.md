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
- `agent/graph/nodes/executor.py`는 `MCP_ENABLED=false`이면 자동으로 `executor_v2.dispatch`로 fallback
- `agent/graph/nodes/executor_v2/`에 MCP 의존성 0건 (grep 확인)
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
- [x] executor_v2의 MCP 의존성 부재 확인 (`agent/graph/nodes/executor_v2/` grep)
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
