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

### 선택한 해결 방식 (Option 2 - 로컬 COPY + ignore-scripts)
- `git clone` 제거 → `COPY mcp/integration_MCP` 로 전환
- `npm ci --ignore-scripts` + `PUPPETEER_SKIP_DOWNLOAD=true` 로 postinstall 훅 차단 (robotjs gyp 컴파일, puppeteer Chromium 다운로드 둘 다 스킵)
- `.dockerignore`에서 `mcp/` 전체 제외 라인 조정 (기존엔 `mcp/` 전체 차단 → COPY가 빈 폴더 될 상태였음)
- `DEBIAN_FRONTEND=noninteractive` 보존 (main의 2da02b7 커밋 내용 — develop에는 없어서 머지 시 유실 위험)
- `uv sync` 2단계 분리(의존성/프로젝트) 포함 — 캐시 효율 ↑

### 대안 검토와 기각 사유
- **Option 1 (`--ignore-scripts`만 추가, git clone 유지)**: CI는 살지만 로컬 통합본 변경이 배포에 반영 안 됨. upstream 의존 계속 유지되는 문제.
- **Option 3 (`dist/` 를 레포에 커밋)**: 런타임에 `node_modules` 필요해서 반쪽짜리. PR diff 노이즈 폭증.
- **Option 4 (alpine에 빌드툴 설치, ignore-scripts 없이 풀 설치)**: robotjs alpine 빌드가 historically 불안정. CI 안정성 오히려 ↓.

### 알려진 한계 (배포 후 후속 조치 필요 시)
- `--ignore-scripts`로 Chromium 미설치. MCP `playtest` 계열 tool (handlers/playtest.ts, utils/playtestHelpers.ts)은 런타임 호출 시 실패함. 현재는 prod에서 호출 안 되는 전제로 통과.
- 이미지에 devDeps(typescript, tsx, vitest 등)도 같이 포함됨. 크기 최적화는 별도 PR로.
- EC2 루트 디스크 압박(overlay2 2.4GB)은 이번 PR 범위 밖 — 아래 "빌드 캐시 자동 정리" 항목에서 별도 처리.

### 검증 체크리스트
- [x] `mcp/integration_MCP/package-lock.json` 존재 확인
- [x] `.dockerignore`의 `mcp/` 차단 라인 조정 필요 확인
- [x] 빌드 필수 파일(`tsconfig.build.json`, `scripts/build-tool-registry.mjs`) 존재 확인
- [x] puppeteer/screenshot-desktop 런타임 사용처 파악 (playtest 계열)
- [ ] 로컬 `docker build -f docker/backend.Dockerfile .` 성공 (사용자 환경에서 확인)

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
